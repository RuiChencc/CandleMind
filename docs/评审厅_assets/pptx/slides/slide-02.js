// slide-02.js -- 问题与定位
const pptxgen = require("pptxgenjs");
const { addPageBadge } = require("./page-badge");
const slideConfig = { type: "content", index: 2, title: "痛点：普通投资者没有专业评审流程" };
function createSlide(pres, theme, total) {
  const slide = pres.addSlide(); slide.background = { color: theme.bg };
  slide.addText(slideConfig.title, { x: 0.6, y: 0.42, w: 8.8, h: 0.55, fontSize: 24, fontFace: theme.font.title, color: theme.primary, bold: true });
  const items = [
    ["专业机构流程", "券商研究所 = 数十名分析师 + 风控委员会 + 卖方共识，个人投资者孤军奋战"],
    ["普通股民现实", "单看 K 线追涨杀跌、听消息、凭直觉 —— 没有多空对抗、没有分歧收敛"],
    ["市场复杂度", "存量博弈 A 股：价值 / 成长 / 游资 / 量化各流派对同一标的观点剧烈冲突"],
    ["AI 时代机会", "把交易公司级别的评审流程，以多智能体形式自动化、可视化、人人可用"]
  ];
  items.forEach((it, i) => {
    const y = 1.25 + i * 0.98;
    slide.addShape(pres.ShapeType.rect, { x: 0.6, y: y, w: 0.09, h: 0.75, fill: { color: i < 3 ? theme.primary : theme.accent }, line: { type: "none" } });
    slide.addText(it[0], { x: 0.85, y: y, w: 2.4, h: 0.75, fontSize: 15, fontFace: theme.font.title, color: theme.secondary, bold: true, valign: "top" });
    slide.addText(it[1], { x: 3.35, y: y - 0.03, w: 6.0, h: 0.85, fontSize: 13, fontFace: theme.font.body, color: theme.dim, valign: "top" });
  });
  addPageBadge(pres, slideConfig.index, total, theme);
  return slide;
}
if (require.main === module) { const pres = new pptxgen(); pres.layout = "LAYOUT_16x9"; createSlide(pres, require("./theme"), 8); pres.writeFile({ fileName: "s2-preview.pptx" }); }
module.exports = { createSlide, slideConfig };