/* radar.js · 流派分歧雷达（纯 SVG 自绘，晨金/玫红） */
const RadarChart = (function(){
  function polar(cx, cy, r, angleDeg){ const a = (angleDeg - 90) * Math.PI / 180; return [cx + r * Math.cos(a), cy + r * Math.sin(a)]; }
  function polyPoints(cx, cy, values, R){
    const n = values.length;
    return values.map((v, i) => polar(cx, cy, R * Math.max(0.03, v) / 100, (360 / n) * i).join(',')).join(' ');
  }
  function render(elId, radar){
    const container = document.getElementById(elId);
    const n = radar.schools.length;
    const W = 380, H = 285, cx = W/2 - 4, cy = H/2 + 6, R = 100;
    let svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" xmlns="http://www.w3.org/2000/svg">';
    svg += '<defs>' +
      '<linearGradient id="rg1" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffc857" stop-opacity=".46"/><stop offset="1" stop-color="#ff8a3c" stop-opacity=".22"/></linearGradient>' +
      '<linearGradient id="rg2" x1="1" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ff5577" stop-opacity=".38"/><stop offset="1" stop-color="#ff8db3" stop-opacity=".16"/></linearGradient>' +
      '</defs>';
    [100, 75, 50, 25].forEach(p => {
      const pts = [];
      for (let i = 0; i < n; i++){ pts.push(polar(cx, cy, R * p / 100, (360 / n) * i).join(',')); }
      svg += '<polygon points="' + pts.join(' ') + '" fill="none" stroke="rgba(255,200,87,' + (p === 100 ? '.24' : '.10') + ')" stroke-width="1"/>';
    });
    for (let i = 0; i < n; i++){
      const [x2, y2] = polar(cx, cy, R, (360 / n) * i);
      svg += '<line x1="' + cx + '" y1="' + cy + '" x2="' + x2.toFixed(1) + '" y2="' + y2.toFixed(1) + '" stroke="rgba(255,200,87,.13)" stroke-width="1"/>';
    }
    svg += '<polygon points="' + polyPoints(cx, cy, radar.rule, R) + '" fill="url(#rg1)" stroke="#ffc857" stroke-width="2"/>';
    svg += '<polygon points="' + polyPoints(cx, cy, radar.agent, R) + '" fill="url(#rg2)" stroke="#ff5577" stroke-width="2" stroke-dasharray="5 3"/>';
    radar.rule.forEach((v, i) => { const [x, y] = polar(cx, cy, R * v / 100, (360 / n) * i); svg += '<circle cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="3.2" fill="#ffc857" stroke="#1a1308" stroke-width="1.2"/>'; });
    radar.agent.forEach((v, i) => { const [x, y] = polar(cx, cy, R * v / 100, (360 / n) * i); svg += '<circle cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="3" fill="#ff5577" stroke="#1a0a10" stroke-width="1.2"/>'; });
    for (let i = 0; i < n; i++){
      const [x, y] = polar(cx, cy, R + 19, (360 / n) * i);
      svg += '<text x="' + x.toFixed(1) + '" y="' + (y + 4).toFixed(1) + '" text-anchor="middle" dominant-baseline="middle" fill="#b8c4d6" font-size="12" font-family="PingFang SC,Microsoft YaHei,sans-serif">' + radar.schools[i] + '</text>';
    }
    svg += '</svg>';
    container.innerHTML = svg;
    document.getElementById('radarLegend').innerHTML =
      '<span class="lg lg-rule">规则引擎</span><span class="lg lg-agent">深度Agent</span>';
  }
  return { render };
})();
