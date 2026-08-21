/* =========================================================
   CDS FIELD TOOLS ／ 地図UI共通スクリプト
   両ツール（防災 / くらし）で共有。
   ========================================================= */
window.CDS = (() => {
  const SOURCE = {
    A:{label:"A｜全国公式", cls:"a", description:"全国共通の公式データを直接取得"},
    B:{label:"B｜オープン", cls:"b", description:"全国オープンデータを出典明示して利用"},
    C:{label:"C｜公式連携", cls:"c", description:"現在地点から公式サービスへ接続"}
  };
  const esc = s => String(s ?? "").replace(/[&<>"']/g, m => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[m]));
  const badge = k => `<span class="source-badge source-${SOURCE[k].cls}">${SOURCE[k].label}</span>`;
  const hav = (a,b,c,d) => {
    const R=6371, da=(c-a)*Math.PI/180, dl=(d-b)*Math.PI/180;
    const q=Math.sin(da/2)**2+Math.cos(a*Math.PI/180)*Math.cos(c*Math.PI/180)*Math.sin(dl/2)**2;
    return 2*R*Math.asin(Math.sqrt(q));
  };
  const dist = km => km < 1 ? `${Math.round(km*1000)}m` : `${km.toFixed(1)}km`;

  /* ---- ピン：白フチ＋濃い塗り。ハザードを重ねても沈まない ---- */
  const pin = (lat, lon, fill, radius=7) =>
    L.circleMarker([lat,lon],{radius,color:"#fff",weight:2.5,fillColor:fill,fillOpacity:1});

  /* ---- 同時実行数を絞った並列ローダー ---- */
  async function runLimited(tasks, limit=6){
    let i=0, total=0;
    const workers = Array.from({length:Math.min(limit,tasks.length)}, async () => {
      while(i < tasks.length){ total += await tasks[i++](); }
    });
    await Promise.all(workers);
    return total;
  }

  /* ---- 連打・連続moveendを間引く ---- */
  const debounce = (fn, ms=300) => {
    let t=null;
    return (...a) => { clearTimeout(t); t=setTimeout(()=>fn(...a), ms); };
  };

  /* ---- 同じ処理が二重に走らないようにする ---- */
  function singleFlight(fn){
    let running=false, queued=false;
    return async function run(){
      if(running){ queued=true; return; }
      running=true;
      try{ await fn(); }
      finally{
        running=false;
        if(queued){ queued=false; run(); }
      }
    };
  }

  /* ---- パネルの折りたたみ／凡例シートを共通配線 ----
     必要なID: #panel #panelBody #collapseBtn #legend #legendBtn  */
  function initPanelChrome(map){
    const panel=document.getElementById("panel");
    const legend=document.getElementById("legend");
    const cBtn=document.getElementById("collapseBtn");
    const lBtn=document.getElementById("legendBtn");
    if(panel && cBtn){
      cBtn.addEventListener("click", () => {
        const closed = panel.classList.toggle("collapsed");
        cBtn.textContent = closed ? "▲" : "▼";
        cBtn.setAttribute("aria-expanded", String(!closed));
        cBtn.title = closed ? "パネルを開く" : "パネルを閉じて地図を広く見る";
        if(map) setTimeout(()=>map.invalidateSize(), 210);
      });
    }
    /* 狭い画面では、長い注意書きを2行に畳んでおく（タップで全文） */
    if(window.matchMedia("(max-width:650px)").matches){
      document.querySelectorAll(".notice, .policyline").forEach(el => {
        el.classList.add("clampable", "clamped");
        el.setAttribute("role", "button");
        el.setAttribute("tabindex", "0");
        el.setAttribute("aria-expanded", "false");
        const toggle = () => {
          const open = !el.classList.toggle("clamped");
          el.setAttribute("aria-expanded", String(open));
        };
        el.addEventListener("click", toggle);
        el.addEventListener("keydown", e => {
          if(e.key === "Enter" || e.key === " "){ e.preventDefault(); toggle(); }
        });
      });
    }

    if(legend && lBtn){
      const close = () => { legend.classList.remove("show"); lBtn.setAttribute("aria-expanded","false"); };
      lBtn.addEventListener("click", () => {
        const shown = legend.classList.toggle("show");
        lBtn.setAttribute("aria-expanded", String(shown));
      });
      legend.addEventListener("click", close);
    }
  }

  /* ---- 位置情報取得。失敗時はalertではなくステータス行へ ---- */
  function locate(onOk, statusEl){
    const say = m => { if(statusEl) statusEl.textContent = m; };
    if(!navigator.geolocation){
      say("このブラウザは位置情報に対応していません。地図を動かして探してください。");
      return;
    }
    say("現在地を取得中…");
    navigator.geolocation.getCurrentPosition(
      p => onOk(p.coords.latitude, p.coords.longitude, p.coords.accuracy),
      () => say("現在地を取得できませんでした。ブラウザの位置情報の許可を確認するか、地図を動かして探してください。"),
      {enableHighAccuracy:true, timeout:10000}
    );
  }

  return {SOURCE,esc,badge,hav,dist,pin,runLimited,debounce,singleFlight,initPanelChrome,locate};
})();
