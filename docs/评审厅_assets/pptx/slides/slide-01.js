// slide-01.js -- 封面
const pptxgen = require("pptxgenjs");
const slideConfig = { type: "cover", index: 1, title: "赛博评审厅", subtitle: "多智能体 AI 金融评审厅 ｜ 华为云码道 Agent 创新赛 · 珠海科技学院站" };
function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };
  slide.addShape(pres.ShapeType.rect, { x: 0, y: 0, w: 10, h: 0.08, fill: { color: theme.primary }, line: { type: "none" } });
  slide.addShape(pres.ShapeType.rect, { x: 0, y: 5.545, w: 10, h: 0.08, fill: { color: theme.accent }, line: { type: "none" } });
  slide.addText("◤◢  REVIEW HALL v2.11", { x: 0.6, y: 1.1, w: 8.8, h: 0.4, fontSize: 14, fontFace: theme.font.body, color: theme.primary, charSpacing: 4 });
  slide.addText(slideConfig.title, { x: 0.6, y: 1.7, w: 8.8, h: 1.1, fontSize: 54, fontFace: theme.font.title, color: theme.secondary, bold: true });
  slide.addShape(pres.ShapeType.rect, { x: 0.62, y: 2.95, w: 2.2, h: 0.05, fill: { color: theme.accent }, line: { type: "none" } });
  slide.addText(slideConfig.subtitle, { x: 0.6, y: 3.2, w: 8.8, h: 0.6, fontSize: 17, fontFace: theme.font.body, color: theme.dim });
  slide.addText("51 位虚拟评委 × 9 类投资风格 × 22 维数据 ｜ 规则引擎 + 多智能体辩论评估", { x: 0.6, y: 4.15, w: 8.8, h: 0.4, fontSize: 13, fontFace: theme.font.body, color: theme.gold });
  slide.addText("核心开发：华为云码道 CodeArts（Spec-Driven + Agent Team）", { x: 0.6, y: 4.8, w: 8.8, h: 0.35, fontSize: 11, fontFace: theme.font.body, color: theme.dim });
  return slide;
}
if (require.main === module) { const pres = new pptxgen(); pres.layout = "LAYOUT_16x9"; createSlide(pres, require("./theme")); pres.writeFile({ fileName: "s1-preview.pptx" }); }
module.exports = { createSlide, slideConfig };