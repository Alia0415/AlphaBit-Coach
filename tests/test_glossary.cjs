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

const requiredTerms = [
  "营业收入",
  "净利润",
  "归母净利润",
  "扣非归母净利润",
  "非经常性损益",
  "经营现金流",
  "资本支出",
  "资产负债率",
  "存货周转率",
  "投入资本回报率",
  "企业价值",
  "现金流折现",
  "社会融资规模",
  "采购经理指数",
  "索提诺比率",
  "产能利用率",
  "信息系数",
];
requiredTerms.forEach((term) => {
  assert.ok(globalThis.AlphaGlossary.lookup(term), `missing glossary term: ${term}`);
});
const screenshotSentence = globalThis.AlphaGlossary.highlightTerms(
  "归母净利润增速落后于收入增速，需要进一步核查成本和费用变化。",
);
assert.match(screenshotSentence, /data-term="归母净利润"/);
assert.match(screenshotSentence, /data-term="收入增速"/);

const allTerms = globalThis.AlphaGlossary.getTerms();
assert.ok(allTerms.length >= 190, `expected at least 190 terms, got ${allTerms.length}`);
assert.equal(new Set(allTerms.map((item) => item.term)).size, allTerms.length);
allTerms.forEach((item) => {
  assert.ok(item.explanation.length >= 12, `explanation too short: ${item.term}`);
});

const registered = globalThis.AlphaGlossary.registerTerms([
  {
    term: "动态测试指标",
    explanation: "这是从当前报告正文动态识别并经过校验的测试指标。",
    category: "报告术语",
  },
]);
assert.equal(registered, 1);
assert.match(
  globalThis.AlphaGlossary.highlightTerms("报告包含动态测试指标。"),
  /data-term="动态测试指标"/,
);
assert.equal(
  globalThis.AlphaGlossary.registerTerms([
    {
      term: '恶意" onclick="alert(1)',
      explanation: "该内容包含不允许出现在术语名称中的属性字符。",
      category: "报告术语",
    },
  ]),
  0,
);

console.log("glossary tests passed");
