// slide-03.js -- 解决方案
const pptxgen = require("pptxgenjs");
const { addPageBadge } = require("./page-badge");
const slideConfig = { type: "content", index: 3, title: "解法：多智能体评审厅 = 交易公司级别的标准化评审" };
function createSlide(pres, theme, total) {
  const slide = pres.addSlide(); slide.background = { color: theme.bg };
  slide.addText(slideConfig.title, { x: 0.6, y: 0.42, w: 8.8, h: 0.55, fontSize: 24, fontFace: theme.font.title, color: theme.primary, bold: true });
  slide.addText("输入股票代码 → 51 位虚拟评委各按自己的投资方法论打分 → 流派分歧可视化 → 多空 3 轮辩论 → 综合判定", { x: 0.6, y: 1.06, w: 8.8, h: 0.4, fontSize: 13, fontFace: theme.font.body, color: theme.gold });
  const steps = [
    ["① 规则引擎骨架分", "22 维数据 × 51 评委 × 180 条量化规则", "确定性 · 秒级 · 零 LLM 依赖"],
    ["② 深度评审 Agent", "4-5 个并行 sub-agent 角色扮演打分", "可覆盖规则分，需附 override_reason"],
    ["③ 分歧检测", "|规则 − Agent| > 30 自动标记", "评审墙红点 + 雷达轴高亮"],
    ["④ 共识汇总", "overall = fund×0.6 + consensus×0.4", "80 / 65 / 50 / 35 四档判定"]
  ];
  steps.forEach((st, i) => {
    const x = 0.6 + (i % 2) * 4.55, y = 1.7 + Math.floor(i / 2) * 1.7;
    slide.addShape(pres.ShapeType.roundRect, { x: x, y: y, w: 4.25, h: 1.5, fill: { color: "101829" }, line: { color: theme.primary, width: 1 }, rectRadius: 0.08 });
    slide.addText(st[0], { x: x + 0.25, y: y + 0.16, w: 3.8, h: 0.45, fontSize: 15, fontFace: theme.font.title, color: theme.primary, bold: true });
    slide.addText(st[1], { x: x + 0.25, y: y + 0.66, w: 3.8, h: 0.5, fontSize: 11, fontFace: theme.font.body, color: theme.secondary });
    slide.addText(st[2], { x: x + 0.25, y: y + 1.08, w: 3.8, h: 0.32, fontSize: 10, fontFace: theme.font.body, color: theme.dim });
  });
  addPageBadge(pres, slideConfig.index, total, theme);
  return slide;
}
if (require.main === module) { const pres = new pptxgen(); pres.layout = "LAYOUT_16x9"; createSlide(pres, require("./theme"), 8); pres.writeFile({ fileName: "s3-preview.pptx" }); }
module.exports = { createSlide, slideConfig };