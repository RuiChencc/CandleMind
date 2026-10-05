// compile.js -- combine slide-*.js into slides/output/presentation.pptx
//
//   node compile.js                              # all slide-*.js, by filename order
//   node compile.js slide-01.js slide-03.js      # explicit subset, in this order
//
// Contract (SKILL.md Step 5/6):
//   * each slide module exports a SYNCHRONOUS createSlide(pres, theme)
//   * canvas is LAYOUT_16x9 = 10" x 5.625"
//   * theme keys: primary / secondary / accent / light / bg  (+ font.title / font.body)
//   * images referenced as ./imgs/<name> resolve against this directory

const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");

const HERE = __dirname;
const OUT_DIR = path.join(HERE, "output");
const THEME = require("./theme");

function discoverModules(cli) {
  if (cli && cli.length) return cli;
  return fs
    .readdirSync(HERE)
    .filter(function (f) { return /^slide-\d+\.js$/.test(f); })
    .sort();
}

function main() {
  const cli = process.argv.slice(2);
  const files = discoverModules(cli);
  if (!files.length) {
    console.error("no slide modules found in " + HERE);
    process.exit(1);
  }

  fs.mkdirSync(OUT_DIR, { recursive: true });
  fs.mkdirSync(path.join(HERE, "imgs"), { recursive: true });

  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";
  pres.author = "pptx-generator";
  pres.title = "presentation";

  const total = files.length;
  let created = 0;
  for (const f of files) {
    const mod = require(path.join(HERE, f));
    if (typeof mod.createSlide !== "function") {
      console.error(f + ": missing synchronous createSlide(pres, theme) export");
      process.exit(1);
    }
    const slide = mod.createSlide(pres, THEME, total);
    if (!slide) {
      console.error(f + ": createSlide returned no slide");
      process.exit(1);
    }
    created++;
    console.log("  " + String(created).padStart(2, "0") + "  " + f);
  }

  const target = path.join(OUT_DIR, "presentation.pptx");
  return pres.writeFile({ fileName: target }).then(function () {
    const bytes = fs.statSync(target).size;
    console.log("");
    console.log("wrote " + target + " (" + created + " slides, " + bytes + " bytes)");
  });
}

main().catch(function (err) {
  console.error(String(err && err.stack ? err.stack : err));
  process.exit(1);
});
