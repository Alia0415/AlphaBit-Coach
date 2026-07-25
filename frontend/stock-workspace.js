import {
  FALLBACK_STOCKS,
  StockLibrary,
  normalizeStoredStocks,
  searchStockCatalog,
} from "./stock-library.js?v=20260726-main-sync2";
import { StockChart } from "./stock-chart.js?v=20260726-main-sync2";

export const SELECTED_STOCK_STORAGE_KEY = "alphabit_selected_stock";

const PERIODS = Object.freeze([
  { value: "1d", label: "日 K", range: "1y" },
  { value: "1w", label: "周 K", range: "3y" },
  { value: "1mo", label: "月 K", range: "5y" },
]);

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function responseJson(response) {
  let payload = {};
  try {
    payload = await response.json();
  } catch (_) {
    payload = {};
  }
  if (!response.ok) {
    const message =
      typeof payload.detail === "string"
        ? payload.detail
        : "暂时无法获取这只股票的行情，请稍后重试。";
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return payload;
}

export function normalizeSelectedStock(stock) {
  return normalizeStoredStocks([stock], 1)[0] || null;
}

export function buildStockResearchPrompt(stock) {
  const normalized = normalizeSelectedStock(stock);
  if (!normalized) return "";
  const board = normalized.board ? `，所属${normalized.board}` : "";
  if (normalized.board === "宽基指数") {
    return [
      `全面分析${normalized.name}（${normalized.symbol}${board}）当前走势及相关信息。`,
      "以最近一年和最新可得数据为主，分析价格趋势、均线、成交量、收益、波动率与最大回撤，",
      "并对成交量异常和可用量化因子进行交叉验证；同时核查指数主要行业与风格暴露、",
      "市场流动性、宏观与政策环境以及主要风险。请形成可阅读的研究报告，标明数据截止日期、",
      "证据来源、不确定性和缺失信息，不提供买卖指令、目标价或收益承诺。",
    ].join("");
  }
  return [
    `全面分析${normalized.name}（${normalized.symbol}${board}）当前的股票走势及相关信息。`,
    "以最近一年和最新可得数据为主，分析价格趋势、均线、成交量、收益、波动率与最大回撤，",
    "并对成交量异常和可用量化因子进行交叉验证；同时核查公司基本面、重要公告或事件、",
    "行业与宏观环境以及主要风险。请形成可阅读的研究报告，标明数据截止日期、证据来源、",
    "不确定性和缺失信息，不提供买卖指令、目标价或收益承诺。",
  ].join("");
}

function readSelectedStock() {
  try {
    return (
      normalizeSelectedStock(
        JSON.parse(localStorage.getItem(SELECTED_STOCK_STORAGE_KEY) || "null"),
      ) || FALLBACK_STOCKS[0]
    );
  } catch (_) {
    return FALLBACK_STOCKS[0];
  }
}

export function rememberSelectedStock(stock) {
  const normalized = normalizeSelectedStock(stock);
  if (!normalized) return null;
  try {
    localStorage.setItem(SELECTED_STOCK_STORAGE_KEY, JSON.stringify(normalized));
  } catch (_) {
    // Selection still works for the current page when storage is unavailable.
  }
  return normalized;
}

export function buildCoachCopy(payload) {
  const periodReturn = Number(payload?.metrics?.period_return);
  const latest = Number(payload?.metrics?.latest_close);
  const ma20Rows = payload?.indicators?.ma20;
  const ma20 = Array.isArray(ma20Rows) && ma20Rows.length
    ? Number(ma20Rows[ma20Rows.length - 1].value)
    : null;
  let direction = "样本不足，暂不判断整体方向";
  if (Number.isFinite(periodReturn)) {
    if (periodReturn > 0.03) direction = "过去一段时间价格整体上涨";
    else if (periodReturn < -0.03) direction = "过去一段时间价格整体下跌";
    else direction = "过去一段时间价格整体震荡";
  }
  let position = "MA20 数据不足，先观察价格和成交量";
  if (Number.isFinite(latest) && Number.isFinite(ma20)) {
    position = latest >= ma20
      ? "最新价格位于 MA20 上方"
      : "最新价格位于 MA20 下方";
  }
  return {
    trend: `${direction}；${position}。这是对已显示区间的确定性描述。`,
    focus: "观察价格与 MA20 的相对位置，以及价格变化时成交量是否同步放大。",
    limit: "历史走势不能证明未来一定上涨或下跌，也不能单独形成买卖信号。",
  };
}

export function mountStockLibraryPage(
  host,
  { onOpenChart = () => {}, notify = () => {} } = {},
) {
  const root = element("div", "stock-page stock-library-page");
  const heading = element("div", "stock-page-heading");
  const titleBlock = element("div");
  titleBlock.append(
    element("span", "stock-page-kicker", "MARKET LIBRARY"),
    element("h1", "", "股票库"),
    element("p", "", "搜索、关注并选择股票，点击后进入独立的大图行情页。"),
  );
  heading.appendChild(titleBlock);

  const selectionHint = element(
    "div",
    "stock-library-selection-hint",
    "选择任意股票查看日 K、周 K、月 K 与读图提示",
  );
  const libraryPanel = element(
    "section",
    "stock-library-panel stock-library-panel-page",
  );
  root.append(heading, selectionHint, libraryPanel);
  host.appendChild(root);

  let selected = readSelectedStock();
  const library = new StockLibrary(libraryPanel, {
    onSelect: (stock) => {
      selected = rememberSelectedStock(stock) || stock;
      library.setSelected(selected);
      onOpenChart(selected);
    },
    onSearch: async (query) => {
      try {
        const response = await fetch(
          `/api/stocks/search?q=${encodeURIComponent(query)}`,
        );
        const payload = await responseJson(response);
        return Array.isArray(payload.stocks) ? payload.stocks : [];
      } catch (_) {
        return searchStockCatalog(query);
      }
    },
    onStorageError: () => notify("浏览器未允许保存关注列表，选股功能仍可正常使用。"),
  });
  library.setSelected(selected);

  library.setStocks(FALLBACK_STOCKS);
  selected =
    FALLBACK_STOCKS.find((stock) => stock.symbol === selected.symbol) || selected;
  rememberSelectedStock(selected);
  library.setSelected(selected);
  return () => library.destroy();
}

export function mountStockChartPage(
  host,
  {
    forceDemo = false,
    initialStock = null,
    onChooseStock = () => {},
    onAnalyzeStock = () => {},
    notify = () => {},
  } = {},
) {
  const root = element("div", "stock-page stock-market-page");
  const heading = element("div", "stock-page-heading stock-market-heading");
  const titleBlock = element("div");
  titleBlock.append(
    element("span", "stock-page-kicker", "MARKET CHART · K-LINE"),
    element("h1", "", "股票行情"),
    element("p", "", "聚焦价格、均线与成交量，只保留 K 线和读图提示。"),
  );
  const chooseButton = element("button", "stock-choose-button", "← 从股票库选股");
  chooseButton.type = "button";
  chooseButton.addEventListener("click", onChooseStock);
  heading.append(titleBlock, chooseButton);

  const workspace = element("div", "stock-market-workspace");
  const chartPanel = element("section", "stock-chart-panel");
  const coachPanel = element("aside", "stock-coach-panel");
  workspace.append(chartPanel, coachPanel);
  root.append(heading, workspace);
  host.appendChild(root);

  const chartHead = element("div", "stock-chart-head");
  const identity = element("div", "stock-identity");
  const name = element("h2", "", "正在加载…");
  const symbol = element("span", "", "—");
  identity.append(name, symbol);
  chartHead.appendChild(identity);

  const toolbar = element("div", "stock-chart-toolbar");
  const periodGroup = element("div", "stock-periods");
  const periodButtons = new Map();
  PERIODS.forEach((period) => {
    const button = element(
      "button",
      `stock-period${period.value === "1d" ? " active" : ""}`,
      period.label,
    );
    button.type = "button";
    button.dataset.period = period.value;
    periodButtons.set(period.value, button);
    periodGroup.appendChild(button);
  });
  const fitButton = element("button", "stock-fit", "适应全部");
  fitButton.type = "button";
  toolbar.append(periodGroup, fitButton);

  const chartShell = element("div", "stock-chart-shell");
  const chartHost = element("div", "stock-chart-canvas");
  const tooltip = element("pre", "stock-chart-tooltip");
  tooltip.hidden = true;
  const state = element("div", "stock-chart-state");
  chartShell.append(chartHost, tooltip, state);
  const legend = element(
    "div",
    "stock-chart-legend",
    "红涨 · 绿跌　MA5 黑 · MA10 深灰 · MA20 浅灰　成交量",
  );
  chartPanel.append(chartHead, toolbar, chartShell, legend);

  coachPanel.append(
    element("span", "stock-coach-kicker", "ALPHA 陪练"),
    element("h2", "", "读图提示"),
  );
  const coachSections = {};
  [
    ["trend", "当前走势"],
    ["focus", "你应该看哪里"],
    ["limit", "不能说明什么"],
  ].forEach(([key, label]) => {
    const section = element("section", "stock-coach-section");
    const body = element("p", "", "等待行情数据。");
    section.append(element("h3", "", label), body);
    coachPanel.appendChild(section);
    coachSections[key] = body;
  });
  const analysisAction = element("section", "stock-analysis-action");
  const analysisButton = element(
    "button",
    "stock-analysis-button",
    "✨ AI 自动分析该股票",
  );
  analysisButton.type = "button";
  analysisButton.addEventListener("click", () => {
    onAnalyzeStock(selected);
  });
  analysisAction.append(
    analysisButton,
    element(
      "p",
      "stock-analysis-copy",
      "进入多 Agent 作战室，综合分析走势、基本面、事件、行业与风险。",
    ),
  );
  coachPanel.appendChild(analysisAction);
  coachPanel.appendChild(
    element(
      "p",
      "stock-coach-disclaimer",
      "仅供研究学习，不构成投资建议或收益承诺。",
    ),
  );

  let selected =
    normalizeSelectedStock(initialStock) ||
    readSelectedStock();
  let selectedPeriod = "1d";
  let requestSequence = 0;
  let controller = null;
  let destroyed = false;
  const chart = new StockChart(chartHost, tooltip);

  name.textContent = selected.name;
  symbol.textContent = selected.symbol;
  rememberSelectedStock(selected);

  async function loadChart() {
    controller?.abort();
    controller = new AbortController();
    const sequence = ++requestSequence;
    setState("loading", "正在加载行情…");
    const period = PERIODS.find((item) => item.value === selectedPeriod);
    const query = new URLSearchParams({
      period: selectedPeriod,
      range: period?.range || "1y",
    });
    if (forceDemo) query.set("demo", "true");
    try {
      const response = await fetch(
        `/api/stocks/${encodeURIComponent(selected.symbol)}/chart?${query}`,
        { signal: controller.signal },
      );
      const payload = await responseJson(response);
      if (destroyed || sequence !== requestSequence) return;
      chart.render(payload);
      updateDetails(payload);
      setState("ready", "");
    } catch (error) {
      if (error?.name === "AbortError" || destroyed || sequence !== requestSequence) return;
      if (!forceDemo && Number(error?.status) >= 500) {
        try {
          query.set("demo", "true");
          const fallbackResponse = await fetch(
            `/api/stocks/${encodeURIComponent(selected.symbol)}/chart?${query}`,
            { signal: controller.signal },
          );
          const fallbackPayload = await responseJson(fallbackResponse);
          if (destroyed || sequence !== requestSequence) return;
          chart.render(fallbackPayload);
          updateDetails(fallbackPayload);
          setState("ready", "");
          notify("实时行情暂不可用，已加载备用行情数据。");
          return;
        } catch (fallbackError) {
          if (
            fallbackError?.name === "AbortError" ||
            destroyed ||
            sequence !== requestSequence
          ) return;
          error = fallbackError;
        }
      }
      chart.destroy();
      setState(
        "error",
        error?.message || "暂时无法获取这只股票的行情，请稍后重试。",
      );
    }
  }

  function updateDetails(payload) {
    const payloadName =
      payload.name && payload.name !== payload.symbol
        ? payload.name
        : selected.name;
    selected =
      normalizeSelectedStock({
        symbol: payload.symbol || selected.symbol,
        name: payloadName || selected.name,
      }) || selected;
    rememberSelectedStock(selected);
    name.textContent = selected.name;
    symbol.textContent = selected.symbol;
    const copy = buildCoachCopy(payload);
    Object.entries(copy).forEach(([key, value]) => {
      coachSections[key].textContent = value;
    });
  }

  function setState(kind, message) {
    state.className = `stock-chart-state ${kind}`;
    state.textContent = message;
    state.hidden = kind === "ready";
  }

  periodButtons.forEach((button, value) => {
    button.addEventListener("click", () => {
      if (selectedPeriod === value) return;
      selectedPeriod = value;
      periodButtons.forEach((candidate, candidateValue) => {
        candidate.classList.toggle("active", candidateValue === value);
      });
      loadChart();
    });
  });
  fitButton.addEventListener("click", () => chart.fitContent());
  loadChart();

  return () => {
    destroyed = true;
    requestSequence += 1;
    controller?.abort();
    chart.destroy();
  };
}
