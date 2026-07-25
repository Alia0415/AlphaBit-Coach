export const RECENT_STORAGE_KEY = "alphabit_recent_stocks";
export const FAVORITE_STORAGE_KEY = "alphabit_favorite_stocks";

export const FALLBACK_STOCKS = Object.freeze([
  { symbol: "000001.SZ", name: "平安银行", market: "SZ" },
  { symbol: "600519.SH", name: "贵州茅台", market: "SH" },
  { symbol: "300750.SZ", name: "宁德时代", market: "SZ" },
  { symbol: "002594.SZ", name: "比亚迪", market: "SZ" },
  { symbol: "601318.SH", name: "中国平安", market: "SH" },
  { symbol: "600036.SH", name: "招商银行", market: "SH" },
  { symbol: "000858.SZ", name: "五粮液", market: "SZ" },
  { symbol: "688981.SH", name: "中芯国际", market: "SH" },
  { symbol: "000300.SH", name: "沪深300", market: "SH" },
  { symbol: "000001.SH", name: "上证指数", market: "SH" },
]);

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
    });
    if (stocks.length >= maxItems) break;
  }
  return stocks;
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
    this.listHost.appendChild(this.renderSection("热门股票", this.stocks));
  }

  renderSection(title, stocks, emptyText = "") {
    const section = node("section", "stock-list-section");
    section.dataset.stockSection = title;
    section.appendChild(node("h3", "", title));
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
      const label = node("span", "stock-row-label");
      label.append(
        node("strong", "", stock.name),
        node("small", "", stock.symbol),
      );
      select.appendChild(label);
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
