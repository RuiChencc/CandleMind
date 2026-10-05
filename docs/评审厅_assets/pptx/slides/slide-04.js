// slide-04.js -- 系统架构
const pptxgen = require("pptxgenjs");
const { addPageBadge } = require("./page-badge");
const slideConfig = { type: "content", index: 4, title: "系统架构：前端评审厅 + 后端规则引擎" };
function createSlide(pres, theme, total) {
  const slide = pres.addSlide(); slide.background = { color: theme.bg };
  slide.addText(slideConfig.title, { x: 0.6, y: 0.42, w: 8.8, h: 0.55, fontSize: 24, fontFace: theme.font.title, color: theme.primary, bold: true });
  const box = (x, y, w, h, title, lines, line) => {
    slide.addShape(pres.ShapeType.roundRect, { x, y, w, h, fill: { color: "101829" }, line: { color: line || theme.primary, width: 1 }, rectRadius: 0.06 });
    slide.addText(title, { x: x + 0.15, y: y + 0.1, w: w - 0.3, h: 0.32, fontSize: 13, fontFace: theme.font.title, color: theme.primary, bold: true });
    slide.addText(lines, { x: x + 0.15, y: y + 0.46, w: w - 0.3, h: h - 0.55, fontSize: 10.5, fontFace: theme.font.body, color: theme.dim });
  };
  box(0.6, 1.3, 4.3, 3.6, "前端 · 赛博评审厅 Dashboard", "51 评委投票墙（逐人点亮动画）\n流派分歧雷达（ECharts 8 轴）\n分歧点高亮 ｜ 多空 3 轮辩论区\n快速档 30s / 深度回放双模式\n（HTML + JS + ECharts · 赛博朋克主题）", theme.primary);
  box(5.1, 1.3, 4.3, 1.7, "后端 · FastAPI 规则引擎", "22 维 × 51 评委 × 180 条规则\n确定性评分 · 秒级 · 零 LLM\noverall = fund×0.6 + consensus×0.4\nverdict 阈值 80/65/50/35", theme.primary);
  box(5.1, 3.15, 4.3, 1.75, "数据层（演示兜底）", "demo_deep.json 预设数据\n600519 茅台 / 000001 平安银行\n300750 宁德时代\n非实时行情 · 教学演示用途", theme.gold);
  slide.addText("①② 华为云码道 CodeArts 生成 ｜ ③ GitCode 公开仓库证据链", { x: 0.6, y: 5.02, w: 8.8, h: 0.35, fontSize: 11, fontFace: theme.font.body, color: theme.gold });
  addPageBadge(pres, slideConfig.index, total, theme);
  return slide;
}
if (require.main === module) { const pres = new pptxgen(); pres.layout = "LAYOUT_16x9"; createSlide(pres, require("./theme"), 8); pres.writeFile({ fileName: "s4-preview.pptx" }); }
module.exports = { createSlide, slideConfig };