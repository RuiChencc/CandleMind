/* extras.js · v3.1/3.2 扩展：切换带 / 流水线 / 对比矩阵 / 流派势力 / 评审历史 / 报告导出 */
const ReviewExt = (function(){
  const stocks = (window.DEMO_DATA || {}).stocks || {};
  const CODES = Object.keys(stocks);  // 动态：20 只预设标的
  const verdictText = {strong_buy:'值得重仓', hold_like:'可以蹲一蹲', watch:'观望', avoid:'规避'};
  const SCHOOL_COLORS = {
    '经典价值':'#5cd9ff','成长':'#5a8cff','宏观对冲':'#a78bff','技术趋势':'#3eea9b',
    '中国价投':'#ffc857','游资':'#ff6b6b','量化':'#ff5577','Serenity卡位':'#d9b3ff'
  };
  const PIPELINE = [
    {title:'数据采集', sub:'22 维指标 · 实时行情'},
    {title:'规则引擎', sub:'180+ 条量化规则'},
    {title:'评委打分', sub:'51 位虚拟评委 · 8 大流派'},
    {title:'分歧辩论', sub:'高分歧触发 3 轮辩论'},
    {title:'汇总判定', sub:'综合分 · 投资建议'}
  ];
  let currentCode = '600519';
  let pipeTimer = null;
  const history = [];

  function $(id){ return document.getElementById(id); }
  function schoolStats(s){
    const map = {};
    (s.judges || []).forEach(j => { const k = j.school || '其他'; map[k] = (map[k] || 0) + 1; });
    return map;
  }
  function switchTo(code){
    if (!stocks[code]) return;
    currentCode = code;
    renderStrip();
    renderCompare();
    renderSchoolPower(code);
    try { App.load(code); } catch(e){}
    playPipeline();
  }

  /* ===== 个股快速切换带 ===== */
  function renderStrip(){
    const el = $('stockStrip');
    el.innerHTML = CODES.map(code => {
      const s = stocks[code]; if (!s) return '';
      return '<div class="s-stock' + (code === currentCode ? ' active' : '') + '" data-code="' + code + '">' +
        '<div>' +
          '<div class="s-code">' + code + '</div>' +
          '<div class="s-name">' + s.name + '</div>' +
        '</div>' +
        '<div class="s-meta">' +
          '<div class="s-score">' + Math.round(s.overall_score) + '</div>' +
          '<div class="s-verdict ' + s.verdict + '">' + (verdictText[s.verdict] || s.verdict) + '</div>' +
        '</div>' +
      '</div>';
    }).join('');
    el.querySelectorAll('.s-stock').forEach(c => c.addEventListener('click', () => switchTo(c.dataset.code)));
  }

  /* ===== 评审流水线 ===== */
  function renderPipeline(){
    const el = $('pipeline');
    el.innerHTML = PIPELINE.map((p, i) =>
      '<div class="pipe-step" data-step="' + i + '">' +
        '<div class="pipe-num">' + (i + 1) + '</div>' +
        '<div class="pipe-body"><div class="pipe-title">' + p.title + '</div><div class="pipe-sub">' + p.sub + '</div></div>' +
      '</div>').join('');
  }
  function playPipeline(){
    if (pipeTimer) clearInterval(pipeTimer);
    const steps = document.querySelectorAll('.pipe-step');
    steps.forEach(x => x.className = 'pipe-step');
    let i = 0;
    pipeTimer = setInterval(() => {
      if (i >= steps.length){ clearInterval(pipeTimer); pipeTimer = null; return; }
      steps.forEach((x, k) => x.className = 'pipe-step' + (k < i ? ' done' : ''));
      steps[i].classList.add('now');
      i++;
    }, 430);
  }

  /* ===== 三股横向对比 ===== */
  function renderCompare(){
    const el = $('compareGrid');
    el.innerHTML = CODES.map(code => {
      const s = stocks[code]; if (!s) return '';
      const share = Math.round(s.judges.length / 51 * 100);
      const ss = schoolStats(s);
      const rows = [
        {k:'基本面', v:s.fund_score, c:'var(--cyan)'},
        {k:'共识分', v:s.consensus_score, c:'var(--gold)'}
      ];
      return '<div class="c-col' + (code === currentCode ? ' active' : '') + '" data-code="' + code + '">' +
        '<div class="c-head"><span><span class="c-code">' + code + '</span> <span class="c-name">' + s.name + '</span></span><span style="font-size:11px;color:var(--muted2)">' + share + '% 评委参与</span></div>' +
        '<div class="c-big"><span class="n">' + Math.round(s.overall_score) + '</span><span class="u">综合分</span><span class="v ' + s.verdict + '">' + (verdictText[s.verdict] || s.verdict) + '</span></div>' +
        rows.map(r =>
          '<div class="c-row"><span class="k">' + r.k + '</span><span class="n">' + Math.round(r.v) + '</span><span class="c-track"><i class="c-fill" style="width:' + r.v + '%;background:' + r.c + '"></i></span></div>'
        ).join('') +
        '<div class="c-schools"><div style="font-size:11px;color:var(--muted2);margin-bottom:3px">流派分布</div>' +
        Object.keys(ss).map(k =>
          '<div class="c-srow"><span class="c-dot" style="--sc:' + (SCHOOL_COLORS[k] || '#ffc857') + '"></span><span class="c-sname">' + k + '</span><span class="c-strack"><i class="c-sfill" style="--sc:' + (SCHOOL_COLORS[k] || '#ffc857') + ';width:' + (ss[k] / 51 * 100) + '%"></i></span><span style="min-width:16px;text-align:right">' + ss[k] + '</span></div>'
        ).join('') + '</div>' +
      '</div>';
    }).join('');
    el.querySelectorAll('.c-col').forEach(c => c.addEventListener('click', () => switchTo(c.dataset.code)));
  }

  /* ===== v3.2 八大流派势力 ===== */
  function renderSchoolPower(code){
    const el = $('schoolPower'); if (!el) return;
    const s = stocks[code]; if (!s) return;
    const agg = {};
    s.judges.forEach(j => {
      const k = j.school || '其他';
      if (!agg[k]) agg[k] = {n:0, rule:0, agent:0};
      agg[k].n++; agg[k].rule += j.rule_score; agg[k].agent += j.agent_score;
    });
    const entries = Object.keys(agg).map(k => {
      const a = agg[k];
      const avg = Math.round((a.rule + a.agent) / (2 * a.n));
      const bias = avg >= 62 ? 'bull' : avg <= 48 ? 'bear' : 'neutral';
      const biasTxt = avg >= 62 ? '偏多' : avg <= 48 ? '偏空' : '中性';
      return {k, c: SCHOOL_COLORS[k] || '#ffc857', n:a.n, avg, bias, biasTxt};
    }).sort((x, y) => y.avg - x.avg);
    el.innerHTML = entries.map(e =>
      '<div class="sp-item">' +
        '<div class="sp-top"><span class="sp-dot" style="--sc:' + e.c + '"></span><span class="sp-name">' + e.k + '</span><span class="sp-count">' + e.n + ' 位</span></div>' +
        '<div class="sp-row"><span class="sp-avg">' + e.avg + '</span><span class="sp-track"><i class="sp-fill" style="--sc:' + e.c + ';width:' + e.avg + '%"></i></span><span class="sp-bias ' + e.bias + '">' + e.biasTxt + '</span></div>' +
      '</div>').join('');
  }

  /* ===== v3.2 评审历史 ===== */
  function recordHistory(code){
    const s = stocks[code]; if (!s) return;
    const t = new Date();
    const pad = n => (n < 10 ? '0' : '') + n;
    const time = pad(t.getHours()) + ':' + pad(t.getMinutes()) + ':' + pad(t.getSeconds());
    history.unshift({code, name:s.name, overall:Math.round(s.overall_score), verdict:s.verdict, time});
    if (history.length > 12) history.length = 12;
    renderHistory();
  }
  function renderHistory(){
    const el = $('historyList'); if (!el) return;
    el.innerHTML = history.map(h =>
      '<div class="h-item' + (h.code === currentCode ? ' active' : '') + '" data-code="' + h.code + '">' +
        '<span class="h-time">' + h.time + '</span>' +
        '<span class="h-code">' + h.code + '</span>' +
        '<span style="font-family:var(--zh);font-size:12px;color:var(--muted)">' + h.name + '</span>' +
        '<span class="h-verdict ' + h.verdict + '">' + verdictText[h.verdict] + '</span>' +
      '</div>').join('') || '<div style="font-size:12px;color:var(--muted2)">暂无评审记录</div>';
    el.querySelectorAll('.h-item').forEach(c => c.addEventListener('click', () => switchTo(c.dataset.code)));
  }

  /* ===== v3.2 报告导出 ===== */
  function exportReport(){
    const s = stocks[currentCode]; if (!s) return;
    const ss = schoolStats(s);
    const lines = [];
    lines.push('# ' + s.code + ' ' + s.name + ' · 赛博评审厅报告');
    lines.push('');
    lines.push('- 综合分：' + Math.round(s.overall_score) + ' / 100 · ' + verdictText[s.verdict]);
    lines.push('- 基本面：' + s.fund_score + ' · 共识分：' + s.consensus_score);
    lines.push('- 评委：' + s.judges.length + ' 位（' + Object.keys(ss).map(k => k + ' ' + ss[k]).join(' / ') + '）');
    lines.push('');
    lines.push('## 摘要');
    lines.push(s.report.summary);
    lines.push('');
    lines.push('## 支持面');
    s.report.support.forEach(x => lines.push('- ' + x));
    lines.push('');
    lines.push('## 风险面');
    s.report.risk.forEach(x => lines.push('- ' + x));
    lines.push('');
    lines.push('## 入场区间');
    s.report.entry_zone.forEach(x => lines.push('- ' + x));
    lines.push('');
    lines.push('## 分歧点');
    s.judges.filter(j => j.flagged).forEach(j => lines.push('- ' + j.name + '（' + j.school + '）：规则 ' + j.rule_score + ' / AI ' + j.agent_score + ' —— ' + j.headline));
    const md = lines.join('\n');
    const blob = new Blob([md], {type:'text/markdown;charset=utf-8'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = '评审报告_' + s.code + '.md';
    a.click();
    URL.revokeObjectURL(a.href);
    const st = $('statusText');
    if (st) st.textContent = '✓ 报告已导出 · ' + a.download;
  }

  function init(){
    renderStrip();
    renderPipeline();
    renderCompare();
    renderSchoolPower(currentCode);
    recordHistory(currentCode);
    const be = $('btnExport');
    if (be) be.addEventListener('click', exportReport);
    const bc = $('btnClearHistory');
    if (bc) bc.addEventListener('click', () => { history.length = 0; renderHistory(); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  /* 钩住 App.load：输入框 / 回车 / 模式切换等入口也同步势力与历史 */
  try {
    const orig = App.load;
    if (typeof orig === 'function' && !orig.__wrapped) {
      App.load = function(code){
        orig(code);
        currentCode = code;
        renderStrip();
        renderCompare();
        renderSchoolPower(code);
        recordHistory(code);
        playPipeline();
      };
      App.load.__wrapped = true;
    }
  } catch(e){}

  return { switchTo, exportReport };
})();