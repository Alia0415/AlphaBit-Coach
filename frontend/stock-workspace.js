import { FALLBACK_STOCKS, StockLibrary } from "./stock-library.js?v=20260725-s02";
import { StockChart } from "./stock-chart.js?v=20260725-s01";

const PERIODS = Object.freeze([
  { value: "1m", label: "分时", range: "1d" },
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

function formatMetric(value, kind = "number") {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  if (kind === "percent") {
    return `${number > 0 ? "+" : ""}${(number * 100).toFixed(2)}%`;
  }
  return number.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
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

export function researchPrompt(stock) {
  return `请分析 ${stock.symbol} 的市场表现、基本面和主要风险，并用通俗方式解释。`;
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

export function mountStockWorkspace(
  host,
  { forceDemo = false, onResearch = () => {}, notify = () => {} } = {},
) {
  const root = element("div", "stock-page");
  const heading = element("div", "stock-page-heading");
  const titleBlock = element("div");
  titleBlock.append(
    element("span", "stock-page-kicker", "MARKET WORKSPACE · INTERACTIVE CHART"),
    element("h1", "", "股票库与行情走势图"),
    element("p", "", "切换股票和周期，先看确定性数据，再决定是否发起深入研究。"),
  );
  const libraryToggle = element("button", "stock-library-toggle", "☰ 股票库");
  libraryToggle.type = "button";
  heading.append(titleBlock, libraryToggle);

  const workspace = element("div", "stock-workspace");
  const libraryPanel = element("aside", "stock-library-panel");
  const chartPanel = element("section", "stock-chart-panel");
  const coachPanel = element("aside", "stock-coach-panel");
  workspace.append(libraryPanel, chartPanel, coachPanel);
  root.append(heading, workspace);
  host.appendChild(root);

  libraryToggle.addEventListener("click", () => {
    workspace.classList.toggle("library-collapsed");
    libraryToggle.setAttribute(
      "aria-expanded",
      String(!workspace.classList.contains("library-collapsed")),
    );
  });
  libraryToggle.setAttribute("aria-expanded", "true");

  const chartHead = element("div", "stock-chart-head");
  const identity = element("div", "stock-identity");
  const name = element("h2", "", "正在加载…");
  const symbol = element("span", "", "—");
  identity.append(name, symbol);
  const source = element("span", "stock-source", "等待数据");
  chartHead.append(identity, source);

  const metrics = element("div", "stock-metrics");
  const metricNodes = {};
  [
    ["latest_close", "最新价", "number"],
    ["period_return", "区间涨跌", "percent"],
    ["maximum_drawdown", "最大回撤", "percent"],
    ["volatility", "波动率", "percent"],
  ].forEach(([key, label, kind]) => {
    const card = element("div", "stock-metric");
    const value = element("strong", "", "—");
    value.dataset.kind = kind;
    card.append(element("span", "", label), value);
    metrics.appendChild(card);
    metricNodes[key] = value;
  });

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
    "红涨 · 绿跌　MA5　MA10　MA20　成交量",
  );
  const researchButton = element("button", "stock-research-button", "让投研团队深入研究");
  researchButton.type = "button";
  chartPanel.append(
    chartHead,
    metrics,
    toolbar,
    chartShell,
    legend,
    researchButton,
  );

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
  coachPanel.appendChild(
    element(
      "p",
      "stock-coach-disclaimer",
      "仅供研究学习，不构成投资建议或收益承诺。",
    ),
  );

  let selected = FALLBACK_STOCKS[0];
  let selectedPeriod = "1d";
  let requestSequence = 0;
  let controller = null;
  let destroyed = false;
  const chart = new StockChart(chartHost, tooltip);

  const library = new StockLibrary(libraryPanel, {
    onSelect: (stock) => selectStock(stock),
    onSearch: async (query) => {
      const response = await fetch(`/api/stocks/search?q=${encodeURIComponent(query)}`);
      return (await responseJson(response)).stocks || [];
    },
    onStorageError: () => notify("浏览器未允许保存关注列表，图表仍可正常使用。"),
  });

  async function loadStocks() {
    try {
      const response = await fetch("/api/stocks");
      const payload = await responseJson(response);
      library.setStocks(payload.stocks || FALLBACK_STOCKS);
      selected =
        (payload.stocks || []).find((stock) => stock.symbol === selected.symbol) ||
        selected;
    } catch (_) {
      library.setStocks(FALLBACK_STOCKS);
    }
    await selectStock(selected);
  }

  async function selectStock(stock) {
    selected = stock;
    library.setSelected(stock);
    name.textContent = stock.name;
    symbol.textContent = stock.symbol;
    await loadChart();
  }

  async function loadChart() {
    controller?.abort();
    controller = new AbortController();
    const sequence = ++requestSequence;
    setState("loading", "正在加载行情…");
    source.textContent = "加载中";
    source.className = "stock-source loading";
    researchButton.disabled = true;
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
      researchButton.disabled = false;
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
          researchButton.disabled = false;
          notify("PandaData 暂不可用，已加载明确标注的演示数据。");
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
      source.textContent = "加载失败";
      source.className = "stock-source error";
      setState(
        "error",
        error?.message || "暂时无法获取这只股票的行情，请稍后重试。",
      );
    }
  }

  function updateDetails(payload) {
    name.textContent = payload.name || selected.name;
    symbol.textContent = payload.symbol || selected.symbol;
    source.textContent = payload.is_demo ? "演示数据" : payload.data_source || "PandaData";
    source.className = `stock-source ${payload.is_demo ? "demo" : "live"}`;
    Object.entries(metricNodes).forEach(([key, node]) => {
      node.textContent = formatMetric(payload.metrics?.[key], node.dataset.kind);
      node.classList.toggle(
        "positive",
        key === "period_return" && Number(payload.metrics?.[key]) > 0,
      );
      node.classList.toggle(
        "negative",
        key === "period_return" && Number(payload.metrics?.[key]) < 0,
      );
    });
    const copy = buildCoachCopy(payload);
    Object.entries(copy).forEach(([key, value]) => {
      coachSections[key].textContent = value;
    });
    legend.textContent =
      payload.period === "1m"
        ? "分时价格线 · 成交量（演示数据不会冒充实时行情）"
        : "红涨 · 绿跌　MA5　MA10　MA20　成交量";
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
  researchButton.addEventListener("click", () => {
    onResearch(selected, researchPrompt(selected));
  });

  loadStocks();

  return () => {
    destroyed = true;
    requestSequence += 1;
    controller?.abort();
    library.destroy();
    chart.destroy();
  };
}
