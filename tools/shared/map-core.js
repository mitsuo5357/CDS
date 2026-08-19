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
  return {SOURCE,esc,badge,hav,dist};
})();
