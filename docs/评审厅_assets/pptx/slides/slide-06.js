// slide-06.js -- 码道深度 2：Agent Team + 报错修复
const pptxgen = require("pptxgenjs");
const { addPageBadge } = require("./page-badge");
const slideConfig = { type: "content", index: 6, title: "码道使用深度 ②：Agent Team 并行 + 迭代修复" };
function createSlide(pres, theme, total) {
  const slide = pres.addSlide(); slide.background = { color: theme.bg };
  slide.addText(slideConfig.title, { x: 0.6, y: 0.42, w: 8.8, h: 0.55, fontSize: 24, fontFace: theme.font.title, color: theme.primary, bold: true });
  const left = [
    ["Leader 智能编排", "拆解后端/前端/数据三路任务并派发"],
    ["Teammate 自主执行", "持续化独立上下文，双向自由通信"],
    ["共享任务池", "成员自主认领，事件驱动可视化推进"]
  ];
  left.forEach((it, i) => {
    const y = 1.35 + i * 1.15;
    slide.addShape(pres.ShapeType.roundRect, { x: 0.6, y: y, w: 4.1, h: 1.0, fill: { color: "101829" }, line: { color: theme.primary, width: 1 }, rectRadius: 0.06 });
    slide.addText(it[0], { x: 0.85, y: y + 0.14, w: 3.7, h: 0.35, fontSize: 14, fontFace: theme.font.title, color: theme.primary, bold: true });
    slide.addText(it[1], { x: 0.85, y: y + 0.5, w: 3.7, h: 0.42, fontSize: 10.5, fontFace: theme.font.body, color: theme.dim });
  });
  const right = [
    ["报错 → 修复记录 ①", "规则引擎字段缺失 → 码道补全 22 维 schema"],
    ["报错 → 修复记录 ②", "前端雷达轴数超限 → 收敛为 8 轴并加图例"],
    ["验收 → 提交", "curl localhost:8000 实测返回 51 评委 JSON 后入库"]
  ];
  right.forEach((it, i) => {
    const y = 1.35 + i * 1.15;
    slide.addShape(pres.ShapeType.roundRect, { x: 5.0, y: y, w: 4.4, h: 1.0, fill: { color: "101829" }, line: { color: theme.accent, width: 1 }, rectRadius: 0.06 });
    slide.addText(it[0], { x: 5.25, y: y + 0.14, w: 4.0, h: 0.35, fontSize: 14, fontFace: theme.font.title, color: theme.accent, bold: true });
    slide.addText(it[1], { x: 5.25, y: y + 0.5, w: 4.0, h: 0.42, fontSize: 10.5, fontFace: theme.font.body, color: theme.dim });
  });
  slide.addText("截图证据：Agent Team 可视化 + Spec-Driven 三件套 + 报错修复对话时间线", { x: 0.6, y: 4.9, w: 8.8, h: 0.4, fontSize: 12, fontFace: theme.font.body, color: theme.gold });
  addPageBadge(pres, slideConfig.index, total, theme);
  return slide;
}
if (require.main === module) { const pres = new pptxgen(); pres.layout = "LAYOUT_16x9"; createSlide(pres, require("./theme"), 8); pres.writeFile({ fileName: "s6-preview.pptx" }); }
module.exports = { createSlide, slideConfig };