// slide-05.js -- 码道深度 1：Spec-Driven 过程
const pptxgen = require("pptxgenjs");
const { addPageBadge } = require("./page-badge");
const slideConfig = { type: "content", index: 5, title: "码道使用深度 ①：Spec-Driven 三阶段" };
function createSlide(pres, theme, total) {
  const slide = pres.addSlide(); slide.background = { color: theme.bg };
  slide.addText(slideConfig.title, { x: 0.6, y: 0.42, w: 8.8, h: 0.55, fontSize: 24, fontFace: theme.font.title, color: theme.primary, bold: true });
  const phases = [
    ["spec.md 需求规格", "功能列表：51 评委投票墙 / 雷达图 / 分歧检测 / 双模式 / 辩论区", "截图位置：码道 spec 页"],
    ["design.md 方案设计", "前后端架构拆分、API 契约、ECharts 雷达 8 轴数据格式", "截图位置：码道 design 页"],
    ["tasks.md 任务拆解", "后端规则引擎与前端 Dashboard 并行任务、验收标准", "截图位置：码道 tasks 页"]
  ];
  phases.forEach((p, i) => {
    const y = 1.35 + i * 1.35;
    slide.addShape(pres.ShapeType.rect, { x: 0.75, y: y, w: 0.6, h: 0.6, fill: { color: i === 0 ? theme.primary : (i === 1 ? theme.accent : theme.gold) }, line: { type: "none" } });
    slide.addText(String(i + 1), { x: 0.75, y: y + 0.08, w: 0.6, h: 0.45, fontSize: 20, fontFace: theme.font.title, color: "ffffff", bold: true, align: "center" });
    slide.addText(p[0], { x: 1.55, y: y - 0.02, w: 3.2, h: 0.4, fontSize: 15, fontFace: theme.font.title, color: theme.secondary, bold: true });
    slide.addText(p[1], { x: 1.55, y: y + 0.34, w: 6.9, h: 0.6, fontSize: 11.5, fontFace: theme.font.body, color: theme.dim });
    slide.addText(p[2], { x: 6.3, y: y - 0.02, w: 3.1, h: 0.3, fontSize: 9.5, fontFace: theme.font.body, color: theme.gold, align: "right" });
  });
  addPageBadge(pres, slideConfig.index, total, theme);
  return slide;
}
if (require.main === module) { const pres = new pptxgen(); pres.layout = "LAYOUT_16x9"; createSlide(pres, require("./theme"), 8); pres.writeFile({ fileName: "s5-preview.pptx" }); }
module.exports = { createSlide, slideConfig };