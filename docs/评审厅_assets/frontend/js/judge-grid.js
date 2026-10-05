/* judge-grid.js · 51 评委投票墙（投行纸片风头像） */
const JudgeGrid = (function(){
  let el = null;
  const SCHOOL_COLORS = {
    '经典价值':'#5cd9ff','成长':'#5a8cff','宏观对冲':'#a78bff','技术趋势':'#3eea9b',
    '中国价投':'#ffc857','游资':'#ff6b6b','量化':'#ff5577','Serenity卡位':'#d9b3ff'
  };
  function init(domId){ el = document.getElementById(domId); }
  function colorBg(school){
    const c = SCHOOL_COLORS[school] || '#ffc857';
    return 'radial-gradient(circle at 35% 30%, #ffffff 0%, ' + c + ' 38%, ' + c + ' 78%, #2a2010 100%)';
  }
  function render(judges, speed){
    el.innerHTML = '';
    judges.forEach((j, i) => {
      const c = document.createElement('div');
      c.className = 'judge-card' + (j.flagged ? ' flagged' : '');
      const col = SCHOOL_COLORS[j.school] || '#ffc857';
      c.style.setProperty('--school-color', col);
      c.innerHTML =
        '<div class="j-avatar" style="background:' + colorBg(j.school) + '">' + j.name[0] + '</div>' +
        '<div class="j-name" title="' + j.name + '">' + j.name + '</div>' +
        '<div class="j-school">' + j.school + '</div>' +
        '<div class="j-bars">' +
          '<div class="j-row"><span class="jl">R</span><span class="j-track"><i class="j-fill rule" style="width:0%"></i></span></div>' +
          '<div class="j-row"><span class="jl">A</span><span class="j-track"><i class="j-fill agent" style="width:0%"></i></span></div>' +
        '</div>';
      el.appendChild(c);
      setTimeout(() => {
        c.classList.add('show');
        const rr = c.querySelector('.j-fill.rule'), aa = c.querySelector('.j-fill.agent');
        if (rr) rr.style.width = j.rule_score + '%';
        if (aa) aa.style.width = j.agent_score + '%';
      }, i * speed);
    });
  }
  return { init, render };
})();
