// slide-09.js -- 评分标准对齐 · 初赛 100 分自评
const pptxgen = require("pptxgenjs");
const { addPageBadge } = require("./page-badge");
const slideConfig = { type: "checklist", index: 9, title: "评分标准对齐 · 初赛 100 分自评" };
function createSlide(pres, theme, total) {
  const slide = pres.addSlide(); slide.background = { color: theme.bg };
  // 标题
  slide.addText(slideConfig.title, { x: 0.6, y: 0.42, w: 8.8, h: 0.55, fontSize: 22, fontFace: theme.font.title, color: theme.primary, bold: true });
  // 副标题
  slide.addText("对照初赛评分维度逐项自评 · 全部证据见 评分标准对齐自查表.md", { x: 0.6, y: 1.0, w: 8.8, h: 0.3, fontSize: 11, fontFace: theme.font.body, color: theme.dim });
  // 5 行评分维度
  const rows = [
    { dim: "功能完备度",        score: 28, max: 30, hint: "51 评委投票墙/雷达/判定/分歧/辩论/报告/对比/历史 全验证通过", c: theme.primary },
    { dim: "码道深度使用",      score: 20, max: 25, hint: "Spec-Driven 三件套 + Agent Team 并行 · 截图待补（SOP §4）",       c: theme.accent  },
    { dim: "专业贴合与创新",    score: 22, max: 25, hint: "51 评委 × 8 流派争议评审 · vs TradingAgents-astock 7 分析师",    c: theme.gold    },
    { dim: "技术架构与工程质量", score: 14, max: 15, hint: "纯前端零依赖 + FastAPI 后端 · SVG 自绘 · main.py + test_rule_engine", c: theme.primary },
    { dim: "交付规范性",        score: 4,  max: 5,  hint: "README 可复现 + 提交包结构完整 + 演示视频分镜脚本",                c: theme.gold    }
  ];
  const yBase = 1.55, rowH = 0.62;
  rows.forEach(function (r, i) {
    const y = yBase + i * rowH;
    // 维度名
    slide.addText(r.dim, { x: 0.6, y: y, w: 2.8, h: 0.4, fontSize: 13, fontFace: theme.font.title, color: r.c, bold: true });
    // 分数大字
    slide.addText(r.score + " / " + r.max, { x: 3.4, y: y - 0.05, w: 1.4, h: 0.5, fontSize: 20, fontFace: theme.font.title, color: r.c, bold: true, align: "center" });
    // 进度条底
    slide.addShape(pres.ShapeType.roundRect, { x: 4.9, y: y + 0.15, w: 4.5, h: 0.18, fill: { color: "101829" }, line: { color: r.c, width: 0.5 }, rectRadius: 0.04 });
    // 进度条填充
    const fillW = (r.score / r.max * 4.5).toFixed(2);
    slide.addShape(pres.ShapeType.roundRect, { x: 4.9, y: y + 0.15, w: fillW, h: 0.18, fill: { color: r.c }, line: { color: r.c, width: 0 }, rectRadius: 0.04 });
    // 证据一句话
    slide.addText(r.hint, { x: 4.9, y: y + 0.36, w: 4.5, h: 0.22, fontSize: 9, fontFace: theme.font.body, color: theme.dim });
  });
  // 底部合计
  slide.addText("合计自评 88 / 100 · 待 D16-D18 补齐码道 8 项截图证据后预估 92+", { x: 0.6, y: 5.05, w: 8.8, h: 0.35, fontSize: 12, fontFace: theme.font.title, color: theme.gold, bold: true, align: "center" });
  addPageBadge(pres, slideConfig.index, total, theme);
  return slide;
}
if (require.main === module) { const pres = new pptxgen(); pres.layout = "LAYOUT_16x9"; createSlide(pres, require("./theme"), 9); pres.writeFile({ fileName: "s9-preview.pptx" }); }
module.exports = { createSlide, slideConfig };