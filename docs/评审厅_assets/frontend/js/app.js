/* app.js · 主控制器（双模式 · 数据来自 window.DEMO_DATA，零请求） */
const App = (function(){
  const data = (window.DEMO_DATA || {}).stocks || {};
  let mode = 'fast', speed = 42, current = null, debateBusy = false;
  const verdictText = {strong_buy:'值得重仓', hold_like:'可以蹲一蹲', watch:'观望', avoid:'规避'};
  function $(id){ return document.getElementById(id); }
  function setStatus(msg){ $('statusText').textContent = msg; }
  function load(code){
    const s = data[code];
    if (!s){ setStatus('代码 ' + code + ' 不在预设演示数据（' + Object.keys(data).join(' / ') + '）'); return; }
    current = s;
    setStatus('代码 ' + s.code + ' · ' + s.name + ' · 正在生成本期评分（' + s.judges.length + ' 位评委）…');
    $('stockName').textContent = s.code + ' ' + s.name;
    const vb = $('verdictBadge');
    vb.className = 'verdict ' + s.verdict;
    vb.textContent = verdictText[s.verdict] || s.verdict;
    const f = s.fund_score, c = s.consensus_score, o = s.overall_score;
    $('scoreBoard').innerHTML =
      '<div class="s-row"><span class="k">基本面</span><span class="v">' + f + '</span><span class="s-track"><i class="s-fill" style="width:0%;background:linear-gradient(90deg,var(--cyan),var(--blue))" data-w="' + f + '%"></i></span></div>' +
      '<div class="s-row"><span class="k">共识分</span><span class="v">' + c + '</span><span class="s-track"><i class="s-fill" style="width:0%;background:linear-gradient(90deg,var(--gold),#ff8a3c)" data-w="' + c + '%"></i></span></div>' +
      '<div class="s-row overall"><span class="k">综合分</span><span class="v">' + o.toFixed(0) + '</span><span class="s-track"><i class="s-fill" style="width:0%;background:linear-gradient(90deg,var(--cyan),var(--blue))" data-w="' + o + '%"></i></span></div>';
    requestAnimationFrame(() => requestAnimationFrame(() => {
      document.querySelectorAll('.s-fill').forEach(x => { x.style.width = x.dataset.w; });
    }));
    JudgeGrid.render(s.judges, speed);
    $('disputeList').innerHTML = s.judges.filter(j => j.flagged).map(j =>
      '<div class="d-item"><div class="d-head"><b>⚡ ' + j.name + ' · ' + j.school + '</b><span class="d-score">规则 ' + j.rule_score + ' / AI ' + j.agent_score + '</span></div>' +
      '<div class="d-gap">分歧 ' + Math.abs(j.rule_score - j.agent_score) + ' 分（&gt; 30）</div>' +
      '<div class="d-msg">' + j.headline + '</div></div>'
    ).join('') || '<div class="d-item"><div class="d-gap">本期无分歧点</div></div>';
    setTimeout(() => RadarChart.render('radarChart', s.radar), mode === 'fast' ? 320 : 700);
    const r = s.report;
    $('reportBody').innerHTML =
      '<div class="r-block summary"><h3>摘要</h3><p>' + r.summary + '</p></div>' +
      '<div class="r-block"><h3>支持面</h3><ul>' + r.support.map(x => '<li>' + x + '</li>').join('') + '</ul></div>' +
      '<div class="r-block"><h3>风险面</h3><ul>' + r.risk.map(x => '<li>' + x + '</li>').join('') + '</ul></div>' +
      '<div class="r-block"><h3>入场区间</h3><ul>' + r.entry_zone.map(x => '<li>' + x + '</li>').join('') + '</ul></div>';
    setTimeout(() => setStatus('✓ ' + s.code + ' ' + s.name + ' 评审完成 · 综合分 ' + o.toFixed(0) + ' · ' + verdictText[s.verdict] + '（演示数据）'), mode === 'fast' ? 2200 : 6000);
  }
  function runDebate(){
    if (debateBusy || !current || !current.disputes || !current.disputes.length) return;
    debateBusy = true;
    Debate.play(current.disputes[0]).then(() => { debateBusy = false; });
  }
  function init(){
    Debate.init('debateLog');
    JudgeGrid.init('judgeGrid');
    $('btnGo').addEventListener('click', () => load($('codeInput').value.trim()));
    $('codeInput').addEventListener('keydown', e => { if (e.key === 'Enter') load(e.target.value.trim()); });
    $('btnDebate').addEventListener('click', runDebate);
    $('btnSkip').addEventListener('click', () => { const lg = $('debateLog'); if (lg) lg.innerHTML = ''; debateBusy = false; });
    document.querySelectorAll('.mode-btn').forEach(b => b.addEventListener('click', () => {
      document.querySelectorAll('.mode-btn').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      mode = b.dataset.mode;
      speed = mode === 'fast' ? 42 : 16;
      setStatus(mode === 'fast' ? '快速档 · 规则引擎实跑（30 秒级出结果）' : '深度回放 · 完整分析过程回放');
      if (current) load(current.code);
    }));
    load('600519');
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
  return { load };
})();
