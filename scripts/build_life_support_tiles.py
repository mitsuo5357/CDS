#!/usr/bin/env python3
"""
くらしのおたすけマップ JAPAN ／ Bレイヤー スナップショット生成

OpenStreetMap の日本全国データ（Geofabrik の .osm.pbf）から
トイレ / 車いす / おむつ交換 / 飲み水 / Wi-Fi を抽出し、
ズーム10のGeoJSONタイルとして書き出す。

実行時にOverpassを叩かないための事前生成であり、
公開Overpassの混雑に左右されずに地図を表示することが目的。

前段（GitHub Actions側）:
  osmium tags-filter で対象タグだけに絞る
  osmium export -f geojsonseq で1行1フィーチャに変換
本スクリプト:
  geojsonseq を読み、代表点（ポリゴンは重心）を求めてタイルに割り振る

出力:
  <out>/{z}/{x}/{y}.geojson   タイル本体
  <out>/index.json            存在するタイルの一覧（クライアントの404回避用）
  <out>/meta.json             生成日時・件数・出典表記

データ出典: © OpenStreetMap contributors, ODbL
"""

import argparse
import json
import math
import os
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone

ZOOM = 10  # --zoom で上書き

# 出力を軽くするため、プロパティのキーは1文字に圧縮する。
#   n=name  c=categories  o=opening_hours  f=fee  p=operator  a=access  i=osm id
CAT_TOILET, CAT_ACCESSIBLE, CAT_BABY, CAT_WATER, CAT_WIFI = "t", "a", "b", "w", "i"


def lon2tile(lon: float, z: int) -> int:
    return int((lon + 180.0) / 360.0 * (2 ** z))


def lat2tile(lat: float, z: int) -> int:
    r = math.radians(lat)
    n = 2 ** z
    return int((1.0 - math.asinh(math.tan(r)) / math.pi) / 2.0 * n)


def representative_point(geom):
    """点はそのまま、線・面は座標平均を代表点とする（施設ピン用途では十分）。"""
    if not geom:
        return None
    t = geom.get("type")
    coords = geom.get("coordinates")
    if t == "Point":
        return coords[0], coords[1]

    pts = []

    def walk(c):
        if not c:
            return
        if isinstance(c[0], (int, float)):
            pts.append((c[0], c[1]))
        else:
            for sub in c:
                walk(sub)

    walk(coords)
    if not pts:
        return None
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def categories(tags: dict):
    """map.html 側の cats() と同じ判定ルールに揃えること。"""
    c = []
    if tags.get("amenity") == "toilets":
        c.append(CAT_TOILET)
    wc = tags.get("wheelchair")
    twc = tags.get("toilets:wheelchair")
    if (wc and wc != "no") or (twc and twc != "no"):
        c.append(CAT_ACCESSIBLE)
    if tags.get("changing_table") in ("yes", "limited"):
        c.append(CAT_BABY)
    if tags.get("amenity") == "drinking_water" or tags.get("drinking_water") == "yes":
        c.append(CAT_WATER)
    if tags.get("internet_access") in ("wlan", "yes"):
        c.append(CAT_WIFI)
    return "".join(dict.fromkeys(c))


def fallback_name(cats: str) -> str:
    if CAT_TOILET in cats:
        return "公衆トイレ"
    if CAT_WATER in cats:
        return "飲み水"
    if CAT_BABY in cats:
        return "おむつ交換設備"
    if CAT_WIFI in cats:
        return "Wi-Fi"
    return "施設"


def osm_ref(feature) -> str:
    """'n/123' 形式。@id / @type が無い場合は id 文字列から拾う。"""
    props = feature.get("properties", {}) or {}
    t = feature.get("@type") or props.get("@type") or ""
    i = feature.get("@id") or props.get("@id") or feature.get("id") or ""
    if isinstance(i, str) and "/" in i:
        t, i = i.split("/", 1)
    if not t:
        return ""
    return f"{t[0]}/{i}"


def main():
    global ZOOM
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="osmium export が出した geojsonseq")
    ap.add_argument("--out", required=True, help="タイル出力先ディレクトリ")
    ap.add_argument("--source-date", default="", help="元PBFの日付（YYYY-MM-DD）")
    ap.add_argument("--zoom", type=int, default=ZOOM, help="タイルのズームレベル")
    args = ap.parse_args()
    ZOOM = args.zoom

    tiles = defaultdict(list)
    total = skipped = 0
    per_cat = defaultdict(int)

    with open(args.input, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip().lstrip("\x1e")  # geojsonseq の区切り文字
            if not line:
                continue
            try:
                feat = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue

            tags = feat.get("properties", {}) or {}
            cats = categories(tags)
            if not cats:
                skipped += 1
                continue

            pt = representative_point(feat.get("geometry"))
            if not pt:
                skipped += 1
                continue
            lon, lat = pt
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                skipped += 1
                continue

            props = {
                "n": tags.get("name:ja") or tags.get("name") or fallback_name(cats),
                "c": cats,
            }
            for key, tag in (("o", "opening_hours"), ("f", "fee"),
                             ("p", "operator"), ("a", "access")):
                v = tags.get(tag)
                if v:
                    props[key] = str(v)[:80]
            ref = osm_ref(feat)
            if ref:
                props["i"] = ref

            x, y = lon2tile(lon, ZOOM), lat2tile(lat, ZOOM)
            tiles[(x, y)].append({
                "t": [round(lat, 6), round(lon, 6)],
                "p": props,
            })
            total += 1
            for ch in cats:
                per_cat[ch] += 1

    if not total:
        print("ERROR: 対象フィーチャが0件でした。入力を確認してください。", file=sys.stderr)
        return 1

    if os.path.isdir(args.out):
        shutil.rmtree(args.out)
    os.makedirs(args.out, exist_ok=True)

    index = []
    for (x, y), items in sorted(tiles.items()):
        # 差分を安定させるため、必ず同じ順序で書き出す
        items.sort(key=lambda d: (d["t"][0], d["t"][1], d["p"].get("i", "")))
        d = os.path.join(args.out, str(ZOOM), str(x))
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{y}.geojson"), "w", encoding="utf-8") as fh:
            json.dump({"z": ZOOM, "x": x, "y": y, "f": items},
                      fh, ensure_ascii=False, separators=(",", ":"))
        index.append(f"{ZOOM}/{x}/{y}")

    with open(os.path.join(args.out, "index.json"), "w", encoding="utf-8") as fh:
        json.dump({"zoom": ZOOM, "tiles": index}, fh, separators=(",", ":"))

    meta = {
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "source_date": args.source_date,
        "zoom": ZOOM,
        "features": total,
        "tiles": len(index),
        "by_category": {
            "toilet": per_cat[CAT_TOILET],
            "accessible": per_cat[CAT_ACCESSIBLE],
            "baby": per_cat[CAT_BABY],
            "water": per_cat[CAT_WATER],
            "wifi": per_cat[CAT_WIFI],
        },
        "attribution": "© OpenStreetMap contributors",
        "license": "ODbL 1.0",
        "license_url": "https://www.openstreetmap.org/copyright",
    }
    with open(os.path.join(args.out, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=1)

    size = sum(os.path.getsize(os.path.join(dp, f))
               for dp, _, fs in os.walk(args.out) for f in fs)
    print(f"features={total} skipped={skipped} tiles={len(index)} "
          f"size={size/1048576:.1f}MB")
    print("by_category=" + json.dumps(meta["by_category"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
