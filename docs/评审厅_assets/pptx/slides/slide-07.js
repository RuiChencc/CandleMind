// slide-07.js -- 学术背书 + 创新点
const pptxgen = require("pptxgenjs");
const { addPageBadge } = require("./page-badge");
const slideConfig = { type: "content", index: 7, title: "创新点与理论依据：更细粒度的多智能体辩论评估" };
function createSlide(pres, theme, total) {
  const slide = pres.addSlide(); slide.background = { color: theme.bg };
  slide.addText(slideConfig.title, { x: 0.6, y: 0.42, w: 8.8, h: 0.55, fontSize: 24, fontFace: theme.font.title, color: theme.primary, bold: true });
  const cites = [
    ["ChatEval（清华）", "多智能体辩论评估优于单模型 —— 我们的 4-5 并行评审 Agent 同源于此"],
    ["Multi-Agents-Debate", "多智能体辩论消歧 —— 评审墙 3 轮结构化分歧正是其工程化落地"],
    ["TradingAgents-astock", "A 股 7 分析师 Bull/Bear 辩论 —— 我们扩展为 51 评委 9 流派全覆盖"]
  ];
  cites.forEach((c, i) => {
    const y = 1.3 + i * 1.15;
    slide.addShape(pres.ShapeType.roundRect, { x: 0.6, y: y, w: 8.8, h: 1.0, fill: { color: "101829" }, line: { color: theme.gold, width: 1 }, rectRadius: 0.06 });
    slide.addText(c[0], { x: 0.85, y: y + 0.14, w: 3.0, h: 0.4, fontSize: 15, fontFace: theme.font.title, color: theme.gold, bold: true });
    slide.addText(c[1], { x: 4.0, y: y + 0.12, w: 5.2, h: 0.8, fontSize: 11.5, fontFace: theme.font.body, color: theme.dim, valign: "top" });
  });
  slide.addText("差异点：单 Agent 打分是点估计，本系统是「51 评委 × 分歧检测 × 多空对抗」的分布结构化评审，且核心代码 100% 由华为云码道生成。", { x: 0.6, y: 4.8, w: 8.8, h: 0.6, fontSize: 13, fontFace: theme.font.body, color: theme.primary, bold: true });
  addPageBadge(pres, slideConfig.index, total, theme);
  return slide;
}
if (require.main === module) { const pres = new pptxgen(); pres.layout = "LAYOUT_16x9"; createSlide(pres, require("./theme"), 8); pres.writeFile({ fileName: "s7-preview.pptx" }); }
module.exports = { createSlide, slideConfig };