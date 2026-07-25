import assert from "node:assert/strict";

import {
  FALLBACK_STOCKS,
  FAVORITE_STORAGE_KEY,
  RECENT_STORAGE_KEY,
  STOCK_BOARD_ORDER,
  groupStocksByBoard,
  normalizeStoredStocks,
  searchStockCatalog,
  toggleFavoriteList,
  upsertRecent,
} from "../frontend/stock-library.js";
import {
  buildCoachCopy,
  normalizeSelectedStock,
  SELECTED_STOCK_STORAGE_KEY,
} from "../frontend/stock-workspace.js";

assert.equal(RECENT_STORAGE_KEY, "alphabit_recent_stocks");
assert.equal(FAVORITE_STORAGE_KEY, "alphabit_favorite_stocks");
assert.equal(SELECTED_STOCK_STORAGE_KEY, "alphabit_selected_stock");
assert.equal(FALLBACK_STOCKS.length, 38);
assert.deepEqual(STOCK_BOARD_ORDER, [
  "沪市主板",
  "深市主板",
  "创业板",
  "科创板",
  "宽基指数",
]);

const normalized = normalizeStoredStocks([
  { symbol: "600519.sh", name: "贵州茅台" },
  { symbol: "600519.SH", name: "重复项" },
  { symbol: "bad", name: "非法" },
]);
assert.deepEqual(normalized, [
  {
    symbol: "600519.SH",
    name: "贵州茅台",
    market: "SH",
    board: "沪市主板",
  },
]);

const grouped = groupStocksByBoard(FALLBACK_STOCKS);
assert.equal(grouped.length, 5);
assert.equal(grouped.find((group) => group.board === "科创板").stocks.length, 8);
assert.equal(searchStockCatalog("科创板").length, 8);
assert.equal(searchStockCatalog("寒武纪")[0].symbol, "688256.SH");

let recent = [];
for (let index = 0; index < 10; index += 1) {
  const symbol = `${String(index).padStart(6, "0")}.SZ`;
  recent = upsertRecent(recent, { symbol, name: symbol });
}
assert.equal(recent.length, 8);
assert.equal(recent[0].symbol, "000009.SZ");
recent = upsertRecent(recent, { symbol: "000005.SZ", name: "第五只" });
assert.equal(recent[0].symbol, "000005.SZ");
assert.equal(recent.filter((stock) => stock.symbol === "000005.SZ").length, 1);

let favorites = toggleFavoriteList([], {
  symbol: "600519.SH",
  name: "贵州茅台",
});
assert.equal(favorites.length, 1);
favorites = toggleFavoriteList(favorites, {
  symbol: "600519.SH",
  name: "贵州茅台",
});
assert.deepEqual(favorites, []);

assert.deepEqual(
  normalizeSelectedStock({ symbol: "300750.sz", name: "宁德时代" }),
  {
    symbol: "300750.SZ",
    name: "宁德时代",
    market: "SZ",
    board: "创业板",
  },
);
assert.equal(normalizeSelectedStock({ symbol: "invalid", name: "无效" }), null);

const copy = buildCoachCopy({
  metrics: { period_return: 0.12, latest_close: 120 },
  indicators: { ma20: [{ time: "2026-01-01", value: 100 }] },
});
assert.match(copy.trend, /整体上涨/);
assert.match(copy.trend, /MA20 上方/);
assert.doesNotMatch(Object.values(copy).join(""), /建议买入|建议卖出|目标价/);

console.log("stock frontend state tests passed");
