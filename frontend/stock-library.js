export const RECENT_STORAGE_KEY = "alphabit_recent_stocks";
export const FAVORITE_STORAGE_KEY = "alphabit_favorite_stocks";
export const STOCK_BOARD_ORDER = Object.freeze([
  "沪市主板",
  "深市主板",
  "创业板",
  "科创板",
  "宽基指数",
]);

export const FALLBACK_STOCKS = Object.freeze([
  { symbol: "600519.SH", name: "贵州茅台", market: "SH", board: "沪市主板" },
  { symbol: "601318.SH", name: "中国平安", market: "SH", board: "沪市主板" },
  { symbol: "600036.SH", name: "招商银行", market: "SH", board: "沪市主板" },
  { symbol: "600276.SH", name: "恒瑞医药", market: "SH", board: "沪市主板" },
  { symbol: "601166.SH", name: "兴业银行", market: "SH", board: "沪市主板" },
  { symbol: "600030.SH", name: "中信证券", market: "SH", board: "沪市主板" },
  { symbol: "601888.SH", name: "中国中免", market: "SH", board: "沪市主板" },
  { symbol: "600900.SH", name: "长江电力", market: "SH", board: "沪市主板" },
  { symbol: "600309.SH", name: "万华化学", market: "SH", board: "沪市主板" },
  { symbol: "601899.SH", name: "紫金矿业", market: "SH", board: "沪市主板" },
  { symbol: "000001.SZ", name: "平安银行", market: "SZ", board: "深市主板" },
  { symbol: "000858.SZ", name: "五粮液", market: "SZ", board: "深市主板" },
  { symbol: "002594.SZ", name: "比亚迪", market: "SZ", board: "深市主板" },
  { symbol: "000333.SZ", name: "美的集团", market: "SZ", board: "深市主板" },
  { symbol: "000651.SZ", name: "格力电器", market: "SZ", board: "深市主板" },
  { symbol: "002415.SZ", name: "海康威视", market: "SZ", board: "深市主板" },
  { symbol: "002475.SZ", name: "立讯精密", market: "SZ", board: "深市主板" },
  { symbol: "002714.SZ", name: "牧原股份", market: "SZ", board: "深市主板" },
  { symbol: "002230.SZ", name: "科大讯飞", market: "SZ", board: "深市主板" },
  { symbol: "000725.SZ", name: "京东方A", market: "SZ", board: "深市主板" },
  { symbol: "300750.SZ", name: "宁德时代", market: "SZ", board: "创业板" },
  { symbol: "300059.SZ", name: "东方财富", market: "SZ", board: "创业板" },
  { symbol: "300760.SZ", name: "迈瑞医疗", market: "SZ", board: "创业板" },
  { symbol: "300124.SZ", name: "汇川技术", market: "SZ", board: "创业板" },
  { symbol: "300308.SZ", name: "中际旭创", market: "SZ", board: "创业板" },
  { symbol: "300274.SZ", name: "阳光电源", market: "SZ", board: "创业板" },
  { symbol: "300015.SZ", name: "爱尔眼科", market: "SZ", board: "创业板" },
  { symbol: "300014.SZ", name: "亿纬锂能", market: "SZ", board: "创业板" },
  { symbol: "688981.SH", name: "中芯国际", market: "SH", board: "科创板" },
  { symbol: "688041.SH", name: "海光信息", market: "SH", board: "科创板" },
  { symbol: "688256.SH", name: "寒武纪", market: "SH", board: "科创板" },
  { symbol: "688012.SH", name: "中微公司", market: "SH", board: "科创板" },
  { symbol: "688111.SH", name: "金山办公", market: "SH", board: "科创板" },
  { symbol: "688036.SH", name: "传音控股", market: "SH", board: "科创板" },
  { symbol: "688008.SH", name: "澜起科技", market: "SH", board: "科创板" },
  { symbol: "688169.SH", name: "石头科技", market: "SH", board: "科创板" },
  { symbol: "000300.SH", name: "沪深300", market: "SH", board: "宽基指数" },
  { symbol: "000001.SH", name: "上证指数", market: "SH", board: "宽基指数" },
]);

export function inferStockBoard(symbol) {
  const normalized = String(symbol || "").trim().toUpperCase();
  if (normalized === "000300.SH" || normalized === "000001.SH") return "宽基指数";
  if (/^(688|689)\d{3}\.SH$/.test(normalized)) return "科创板";
  if (/^(300|301)\d{3}\.SZ$/.test(normalized)) return "创业板";
  return normalized.endsWith(".SH") ? "沪市主板" : "深市主板";
}

export function normalizeStoredStocks(value, maxItems = 50) {
  if (!Array.isArray(value)) return [];
  const seen = new Set();
  const stocks = [];
  for (const item of value) {
    const symbol = String(item?.symbol || "").trim().toUpperCase();
    if (!/^\d{6}\.(SH|SZ)$/.test(symbol) || seen.has(symbol)) continue;
    seen.add(symbol);
    stocks.push({
      symbol,
      name: String(item?.name || symbol).trim() || symbol,
      market: symbol.slice(-2),
      board: String(item?.board || inferStockBoard(symbol)).trim() ||
        inferStockBoard(symbol),
    });
    if (stocks.length >= maxItems) break;
  }
  return stocks;
}

export function groupStocksByBoard(stocks) {
  const normalized = normalizeStoredStocks(stocks, 100);
  const groups = new Map(STOCK_BOARD_ORDER.map((board) => [board, []]));
  normalized.forEach((stock) => {
    if (!groups.has(stock.board)) groups.set(stock.board, []);
    groups.get(stock.board).push(stock);
  });
  return [...groups.entries()]
    .filter(([, items]) => items.length)
    .map(([board, items]) => ({ board, stocks: items }));
}

export function searchStockCatalog(query, stocks = FALLBACK_STOCKS) {
  const normalized = String(query || "").trim();
  if (!normalized) return normalizeStoredStocks(stocks, 100);
  const upper = normalized.toUpperCase();
  return normalizeStoredStocks(stocks, 100).filter(
    (stock) =>
      stock.symbol.includes(upper) ||
      stock.name.includes(normalized) ||
      stock.board.includes(normalized),
  );
}

export function upsertRecent(stocks, stock, maxItems = 8) {
  return normalizeStoredStocks(
    [stock, ...normalizeStoredStocks(stocks)].filter(
      (item, index, rows) =>
        rows.findIndex((candidate) => candidate.symbol === item.symbol) === index,
    ),
    maxItems,
  );
}

export function toggleFavoriteList(stocks, stock) {
  const normalized = normalizeStoredStocks(stocks);
  const exists = normalized.some((item) => item.symbol === stock.symbol);
  return exists
    ? normalized.filter((item) => item.symbol !== stock.symbol)
    : normalizeStoredStocks([stock, ...normalized]);
}

function readStorage(key, maxItems) {
  try {
    return normalizeStoredStocks(JSON.parse(localStorage.getItem(key) || "[]"), maxItems);
  } catch (_) {
    return [];
  }
}

function writeStorage(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (_) {
    // Storage may be disabled. Chart selection remains fully functional.
  }
}

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

export class StockLibrary {
  constructor(root, { onSelect, onSearch, onStorageError } = {}) {
    this.root = root;
    this.onSelect = onSelect || (() => {});
    this.onSearch = onSearch || (async () => FALLBACK_STOCKS);
    this.onStorageError = onStorageError || (() => {});
    this.stocks = [...FALLBACK_STOCKS];
    this.searchResults = null;
    this.selectedSymbol = "";
    this.recent = readStorage(RECENT_STORAGE_KEY, 8);
    this.favorites = readStorage(FAVORITE_STORAGE_KEY, 50);
    this.searchTimer = null;
    this.searchSequence = 0;
    this.render();
  }

  setStocks(stocks) {
    const normalized = normalizeStoredStocks(stocks);
    this.stocks = normalized.length ? normalized : [...FALLBACK_STOCKS];
    const metadata = new Map(this.stocks.map((stock) => [stock.symbol, stock]));
    this.recent = normalizeStoredStocks(
      this.recent.map((stock) => metadata.get(stock.symbol) || stock),
      8,
    );
    this.favorites = normalizeStoredStocks(
      this.favorites.map((stock) => metadata.get(stock.symbol) || stock),
      50,
    );
    writeStorage(RECENT_STORAGE_KEY, this.recent);
    writeStorage(FAVORITE_STORAGE_KEY, this.favorites);
    this.renderLists();
  }

  setSelected(stock) {
    this.selectedSymbol = stock.symbol;
    this.recent = upsertRecent(this.recent, stock);
    writeStorage(RECENT_STORAGE_KEY, this.recent);
    this.renderLists();
  }

  toggleFavorite(stock) {
    try {
      this.favorites = toggleFavoriteList(this.favorites, stock);
      writeStorage(FAVORITE_STORAGE_KEY, this.favorites);
      this.renderLists();
    } catch (_) {
      this.onStorageError();
    }
  }

  render() {
    this.root.innerHTML = "";
    const heading = node("div", "stock-library-heading");
    heading.append(
      node("span", "stock-library-kicker", "MARKET LIBRARY"),
      node("h2", "", "股票库"),
    );
    const search = node("label", "stock-search");
    search.append(node("span", "sr-only", "搜索股票"));
    this.searchInput = node("input");
    this.searchInput.type = "search";
    this.searchInput.placeholder = "代码 / 名称 / 完整证券代码";
    this.searchInput.autocomplete = "off";
    this.searchInput.addEventListener("input", () => this.scheduleSearch());
    search.appendChild(this.searchInput);
    this.listHost = node("div", "stock-library-lists");
    this.root.append(heading, search, this.listHost);
    this.renderLists();
  }

  scheduleSearch() {
    clearTimeout(this.searchTimer);
    const query = this.searchInput.value.trim();
    if (!query) {
      this.searchResults = null;
      this.renderLists();
      return;
    }
    const sequence = ++this.searchSequence;
    this.searchTimer = setTimeout(async () => {
      this.searchInput.classList.add("searching");
      try {
        const results = await this.onSearch(query);
        if (sequence !== this.searchSequence) return;
        this.searchResults = normalizeStoredStocks(results);
      } catch (_) {
        if (sequence !== this.searchSequence) return;
        this.searchResults = [];
      } finally {
        if (sequence === this.searchSequence) {
          this.searchInput.classList.remove("searching");
          this.renderLists();
        }
      }
    }, 240);
  }

  renderLists() {
    if (!this.listHost) return;
    this.listHost.innerHTML = "";
    if (this.searchResults !== null) {
      this.listHost.appendChild(
        this.renderSection(
          "搜索结果",
          this.searchResults,
          "没有匹配的股票，请尝试完整代码。",
        ),
      );
      return;
    }
    if (this.recent.length) {
      this.listHost.appendChild(this.renderSection("最近查看", this.recent));
    }
    if (this.favorites.length) {
      this.listHost.appendChild(this.renderSection("我的关注", this.favorites));
    }
    this.listHost.appendChild(
      node("div", "stock-board-directory-title", "按交易板块浏览"),
    );
    groupStocksByBoard(this.stocks).forEach(({ board, stocks }) => {
      this.listHost.appendChild(
        this.renderSection(board, stocks, "", "board"),
      );
    });
  }

  renderSection(title, stocks, emptyText = "", kind = "standard") {
    const section = node(
      "section",
      `stock-list-section${kind === "board" ? " stock-board-section" : ""}`,
    );
    section.dataset.stockSection = title;
    const heading = node("div", "stock-list-section-heading");
    heading.append(
      node("h3", "", title),
      node("span", "stock-list-count", `${stocks.length} 支`),
    );
    section.appendChild(heading);
    if (!stocks.length) {
      section.appendChild(node("p", "stock-list-empty", emptyText || "暂无股票"));
      return section;
    }
    const list = node("div", "stock-list");
    stocks.forEach((stock) => {
      const row = node(
        "div",
        `stock-row${stock.symbol === this.selectedSymbol ? " selected" : ""}`,
      );
      row.dataset.symbol = stock.symbol;
      const select = node("button", "stock-row-main");
      select.type = "button";
      select.title = `查看 ${stock.name} K 线行情`;
      select.setAttribute("aria-label", select.title);
      const label = node("span", "stock-row-label");
      const metadata = node("span", "stock-row-meta");
      label.append(
        node("strong", "", stock.name),
      );
      metadata.append(
        node("small", "", stock.symbol),
        node("em", "stock-board-badge", stock.board),
      );
      label.appendChild(metadata);
      select.append(label, node("span", "stock-row-action", "查看行情 →"));
      select.addEventListener("click", () => this.onSelect(stock));

      const favorite = node(
        "button",
        `stock-favorite${this.isFavorite(stock.symbol) ? " active" : ""}`,
        this.isFavorite(stock.symbol) ? "★" : "☆",
      );
      favorite.type = "button";
      favorite.title = this.isFavorite(stock.symbol) ? "取消关注" : "加入关注";
      favorite.setAttribute("aria-label", favorite.title);
      favorite.addEventListener("click", () => this.toggleFavorite(stock));
      row.append(select, favorite);
      list.appendChild(row);
    });
    section.appendChild(list);
    return section;
  }

  isFavorite(symbol) {
    return this.favorites.some((stock) => stock.symbol === symbol);
  }

  destroy() {
    clearTimeout(this.searchTimer);
    this.searchSequence += 1;
  }
}
