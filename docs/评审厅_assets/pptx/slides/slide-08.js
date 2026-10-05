// slide-08.js -- 现场演示 + 商业前景
const pptxgen = require("pptxgenjs");
const { addPageBadge } = require("./page-badge");
const slideConfig = { type: "summary", index: 8, title: "现场演示与未来展望" };
function createSlide(pres, theme, total) {
  const slide = pres.addSlide(); slide.background = { color: theme.bg };
  slide.addText(slideConfig.title, { x: 0.6, y: 0.42, w: 8.8, h: 0.55, fontSize: 24, fontFace: theme.font.title, color: theme.primary, bold: true });
  slide.addText("① 快速档（30 秒实跑）", { x: 0.6, y: 1.25, w: 4.3, h: 0.4, fontSize: 15, fontFace: theme.font.title, color: theme.primary, bold: true });
  slide.addText("输入 600519 → 规则引擎 51 评委骨架分 → 投票墙逐人点亮 → 雷达 8 轴 → 分歧点出现 → 综合判定 66.92 分「可以蹲一蹲」", { x: 0.6, y: 1.7, w: 4.3, h: 1.6, fontSize: 12, fontFace: theme.font.body, color: theme.secondary });
  slide.addText("② 深度回放（预生成分析）", { x: 0.6, y: 3.4, w: 4.3, h: 0.4, fontSize: 15, fontFace: theme.font.title, color: theme.accent, bold: true });
  slide.addText("切换 000001 / 300750 → 完整过程回放 → 多空 3 轮辩论 → 评审报告（支持面/风险面/入场区间）", { x: 0.6, y: 3.85, w: 4.3, h: 1.3, fontSize: 12, fontFace: theme.font.body, color: theme.secondary });
  slide.addShape(pres.ShapeType.roundRect, { x: 5.2, y: 1.25, w: 4.2, h: 4.0, fill: { color: "101829" }, line: { color: theme.primary, width: 1 }, rectRadius: 0.08 });
  slide.addText("展望", { x: 5.45, y: 1.45, w: 3.7, h: 0.4, fontSize: 15, fontFace: theme.font.title, color: theme.gold, bold: true });
  slide.addText("• 接入实时行情，规则引擎动态评分\n• 评委名单可扩展（个人自定义流派）\n• 从个股扩展到组合 / 行业对比\n• 沉淀「人人可用的 AI 评审」SaaS 原型", { x: 5.45, y: 1.9, w: 3.75, h: 2.2, fontSize: 13, fontFace: theme.font.body, color: theme.secondary, lineSpacing: 18 });
  slide.addText("REDUCE NOISE · SHOW DIVERGENCE · TRUST THE PANEL", { x: 0.6, y: 5.05, w: 8.8, h: 0.35, fontSize: 10, fontFace: theme.font.body, color: theme.dim, charSpacing: 3 });
  addPageBadge(pres, slideConfig.index, total, theme);
  return slide;
}
if (require.main === module) { const pres = new pptxgen(); pres.layout = "LAYOUT_16x9"; createSlide(pres, require("./theme"), 8); pres.writeFile({ fileName: "s8-preview.pptx" }); }
module.exports = { createSlide, slideConfig };