// page-badge.js -- bottom-right page number badge.
// Every slide EXCEPT the cover must include one (SKILL.md Step 5 rule 8).
// Canvas is LAYOUT_16x9 = 10" x 5.625".
function addPageBadge(pres, index, total, theme) {
  const slide = pres.slides[pres.slides.length - 1];
  const w = 0.62, h = 0.26;
  const xAt = 10 - 0.42 - w;
  const yAt = 5.625 - 0.34 - h;
  slide.addShape(pres.ShapeType.rect, {
    x: xAt, y: yAt, w: w, h: h,
    fill: { color: theme.accent },
    line: { type: "none" },
  });
  slide.addText(index + " / " + total, {
    x: xAt, y: yAt, w: w, h: h,
    fontSize: 9, fontFace: theme.font ? theme.font.body : "Microsoft YaHei",
    color: theme.bg, align: "center", valign: "mid", margin: 0,
  });
  return slide;
}

module.exports = { addPageBadge };
