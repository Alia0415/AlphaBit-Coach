import assert from "node:assert/strict";

import {
  applyClarificationOption,
  buildQueryContext,
} from "../frontend/office/js/query-refinement.js";

assert.equal(
  applyClarificationOption(
    "分析宁德时代近期的经营表现与主要风险",
    "近1年",
    "time_range",
  ),
  "分析宁德时代近1年的经营表现与主要风险",
);
assert.equal(
  applyClarificationOption(
    "分析宁德时代的经营表现与主要风险",
    "近3年",
    "time_range",
  ),
  "分析宁德时代的经营表现与主要风险；时间范围为近3年",
);
assert.equal(
  applyClarificationOption("保持原问题", "选项", "unsupported"),
  "保持原问题",
);
assert.deepEqual(
  buildQueryContext("口语原问题", "专业改写", "用户最终编辑"),
  {
    originalQuery: "口语原问题",
    rewrittenQuery: "专业改写",
    finalQuery: "用户最终编辑",
  },
);

console.log("query refinement tests passed");
