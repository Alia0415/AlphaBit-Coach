const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "glossary.js"),
  "utf8",
);
vm.runInThisContext(source, { filename: "frontend/glossary.js" });

const highlighted = globalThis.AlphaGlossary.highlightTerms(
  "策略最大回撤为 12%，需要关注夏普比率。",
);

assert.match(highlighted, /data-term="最大回撤"/);
assert.match(highlighted, /data-term="夏普比率"/);
assert.match(highlighted, /tabindex="0"/);
assert.doesNotMatch(
  globalThis.AlphaGlossary.highlightTerms("AlphaOS"),
  /data-term="Alpha"/,
);

console.log("glossary tests passed");
