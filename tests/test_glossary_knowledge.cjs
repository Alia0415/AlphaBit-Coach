const assert = require("node:assert/strict");
const path = require("node:path");

delete globalThis.AlphaGlossary;
require(path.join(__dirname, "..", "frontend", "glossary.js"));

const glossary = globalThis.AlphaGlossary;
assert.ok(glossary, "AlphaGlossary should be exported globally");

const registered = glossary.setResearchEntries([
  {
    term: "营业收入同比增速",
    color: "var(--cyan)",
    explanation: (
      "Revenue YoY。衡量本期营业收入相较去年同期的变化。" +
      "计算方式：本期营业收入 / 上年同期营业收入 - 1。" +
      "本次结果：-1.21%。使用局限：单期变化不代表长期趋势。"
    ),
  },
  {
    term: "不安全颜色测试",
    color: "url(javascript:alert(1))",
    explanation: "颜色必须回退到安全主题色。",
  },
]);

assert.equal(registered, 2);
assert.match(
  glossary.lookup("营业收入同比增速").explanation,
  /本次结果：-1\.21%/,
);
assert.equal(
  glossary.lookup("不安全颜色测试").color,
  "var(--cyan)",
);

const highlighted = glossary.highlightTerms(
  "营业收入同比增速为 -1.21%，仍需结合现金流验证。",
);
assert.match(highlighted, /class="glossary-term"/);
assert.match(highlighted, /data-term="营业收入同比增速"/);
assert.doesNotMatch(highlighted, /javascript:/);

glossary.setResearchEntries([]);
assert.equal(glossary.lookup("营业收入同比增速"), undefined);

console.log("glossary knowledge tests passed");
