/* debate.js · 多空辩论区（打字机回放） */
const Debate = (function(){
  let log = null;
  function init(domId){ log = document.getElementById(domId); }
  function clear(){ if (log) log.innerHTML = ''; }
  function typeLine(line){
    return new Promise(res => {
      const div = document.createElement('div');
      div.className = 'msg ' + line.cls;
      div.innerHTML = '<span class="who">' + line.who + '</span><span class="t"></span><span class="cursor"></span>';
      log.appendChild(div);
      log.scrollTop = log.scrollHeight;
      const t = div.querySelector('.t');
      let i = 0;
      const iv = setInterval(() => {
        t.textContent += line.text[i++];
        log.scrollTop = log.scrollHeight;
        if (i >= line.text.length){ clearInterval(iv); const c = div.querySelector('.cursor'); if (c) c.remove(); res(); }
      }, 22);
    });
  }
  async function play(dispute){
    clear();
    const lines = [
      {who: dispute.bull_name + ' · 多方（' + dispute.bull_score + ' 分）', cls: 'bull', text: dispute.transcript[0]},
      {who: dispute.bear_name + ' · 空方（' + dispute.bear_score + ' 分）', cls: 'bear', text: dispute.transcript[1]},
      {who: dispute.bull_name + ' · 多方回应', cls: 'bull', text: dispute.transcript[2]},
      {who: '评审团判定', cls: 'verdict-msg', text: '观点对抗已收敛，分歧点已标记，综合判定见评审报告。'}
    ];
    for (const line of lines){ await typeLine(line); }
  }
  return { init, play };
})();
