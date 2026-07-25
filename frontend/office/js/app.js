// AlphaOS Pixel Office — application shell + router.
// Renders the sidebar / topbar / statusbar chrome and the page outlet.
// Local example data remains available for internal validation, but the
// product entrypoint is the live research workflow.
import { store } from "./store.js";
import {
  maybeStartProfileOnboarding,
  mountProfilePage,
  openProfileOnboarding,
} from "./profile.js?v=20260724-p03";
import {
  AGENTS,
  DEMO_SKILLS,
  REPORTS,
  OFFICE_FEED,
  TEAM_RADAR,
  RECOMMENDED_GROUPS,
  CLARIFY_GROUPS,
  ANALYSIS_SCOPE,
  DEMO_TASK,
  WAR_SCRIPT,
  SKILL_FINAL_COUNTS,
  HISTORY_TASKS,
  DEMO_COMPANION,
  DEMO_COACH,
} from "./mock.js?v=20260725-p07";
import { companionAdapter, renderCompanionCard } from "./companion.js?v=20260725-p05";
import {
  isLive,
  connectivity,
  fetchExperts,
  fetchSkills,
  fetchOverview,
  fetchTasks,
  fetchReports,
  fetchReport,
  extractReportGlossary,
  setExpertEnabled as liveSetExpertEnabled,
  submitReportFollowup,
  askCoach,
  fetchCoachGuide,
  fetchCoachNarrations,
  rewriteResearchQuery as liveRewriteResearchQuery,
  startResearchRun,
  openResearchRunStream,
  clarifySession as liveClarifySession,
  openTaskStream,
  mapPlan,
  roleFor as liveRoleFor,
} from "./live.js?v=20260726-research-run";
import {
  attachSelectionQuoting,
  buildCoachSidebar,
  createClassroomPanel,
} from "./coach.js?v=20260726-coach-fold";
import {
  buildOfficeGlossaryPage,
  highlightGlossaryScope,
  initOfficeGlossary,
  registerGlossaryTerms,
} from "./glossary-ui.js?v=20260726-full-page";
import {
  buildStockResearchPrompt,
  buildStockWorkflowContext,
  mountStockChartPage,
  mountStockLibraryPage,
} from "../../stock-workspace.js?v=20260726-backend-search2";
import {
  applyClarificationOption,
  buildQueryContext,
} from "./query-refinement.js?v=20260726-query-refine";

const researchPresentation = globalThis.AlphaResearchPresentation;

const PUBLIC_RESEARCH_METHODS = Object.freeze({
  factor_idea_generation: {
    name: "因子研究假设",
    description: "把市场现象转化为可以检验的量化假设，并明确后续验证边界。",
  },
  r020_volume_expansion: {
    name: "成交量扩张分析",
    description: "观察成交活跃度变化，并结合收益、波动和样本范围判断其研究意义。",
  },
  a_share_stock_dossier: {
    name: "A 股公司基本面尽调",
    description: "综合已披露财务信息、审计意见和业绩线索，形成公司基本面证据档案。",
  },
  macro_monitor: {
    name: "宏观环境监测",
    description: "跟踪经济、利率、流动性与政策环境，解释它们向行业和公司的传导路径。",
  },
  event_risk_alert: {
    name: "公司事件风险核查",
    description: "核查可能影响研究结论的公司事件，并区分已发生风险与待验证信号。",
  },
});

const PUBLIC_AGENT_CAPABILITIES = Object.freeze({
  research: ["财务报表阅读", "基本面分析", "盈利质量验证", "多期趋势比较"],
  quant: ["量化研究假设", "样本与因子分析", "收益风险评估", "过拟合与成本检查"],
  macro: ["经济周期判断", "利率与流动性分析", "政策传导研究", "行业景气观察"],
  risk: ["反对证据核查", "缺失证据识别", "结论强度控制", "事件风险验证"],
  report: ["多专家证据整合", "冲突观点处理", "结论措辞校准", "研究局限说明"],
});

function safePublicText(value, fallback = "") {
  if (researchPresentation?.publicText) {
    return researchPresentation.publicText(value, fallback);
  }
  const text = String(value ?? "")
    .replace(
      /PandaData|get_(?:fina|stock)_[A-Za-z0-9_]+|https?:\/\/\S+|\/api\/\S+|\b(?:DeepSeek|Volcano Ark|model|SSE)\b/gi,
      "专业数据服务",
    )
    .replace(/\b[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+\b/g, "专业研究方法")
    .replace(/\bskill\b/gi, "研究能力")
    .trim();
  return text || fallback;
}

function publicResearchMethod(value) {
  const item = value && typeof value === "object" ? value : { id: value };
  const key = String(item.id || value || "");
  const known = PUBLIC_RESEARCH_METHODS[key];
  if (known) return known;
  return {
    name: safePublicText(item.name, "专业研究方法"),
    description: safePublicText(
      item.description,
      "用于完成本次研究中的一项专业分析，并保留证据边界。",
    ),
  };
}

function publicAgentCapabilities(agent) {
  const known = PUBLIC_AGENT_CAPABILITIES[String(agent?.id || "")];
  if (known) return known;
  return (agent?.capabilities || [])
    .map((item) => safePublicText(item))
    .filter(Boolean)
    .slice(0, 6);
}

function publicAgentMethods(agent) {
  return (agent?.skills || [])
    .map((item) => publicResearchMethod(item))
    .filter((item, index, all) => all.findIndex((other) => other.name === item.name) === index);
}

// Live planning session shared across hall → clarify → war room. The planning
// phase is explicit so the war room can open immediately without inventing a
// selected Agent or DAG before the real Manager response arrives.
let liveSession = {
  runId: null,
  taskId: null,
  prompt: "",
  plan: null,
  researchState: null,
  connectionIssue: false,
  phase: "idle",
  error: null,
  originalQuery: "",
  rewrittenQuery: "",
  finalQuery: "",
  workflowMode: "dynamic",
  stockSymbol: "",
  stockName: "",
  stockBoard: "",
};
let livePlanningSource = null;
function setLiveSession(next) { liveSession = { ...liveSession, ...next }; }
function resetLiveSession() {
  if (livePlanningSource) {
    try { livePlanningSource.close(); } catch (_) {}
    livePlanningSource = null;
  }
  liveSession = {
    runId: null,
    taskId: null,
    prompt: "",
    plan: null,
    researchState: null,
    connectionIssue: false,
    phase: "idle",
    error: null,
    originalQuery: "",
    rewrittenQuery: "",
    finalQuery: "",
    workflowMode: "dynamic",
    stockSymbol: "",
    stockName: "",
    stockBoard: "",
  };
}

function beginLiveResearch(prompt, queryContext = {}) {
  const normalizedPrompt = String(prompt || "").trim();
  if (!normalizedPrompt) {
    toast("请先描述你的研究意向");
    return;
  }
  const switchedToLive = !isLive();
  if (switchedToLive) store.set({ mode: "live" });
  resetLiveSession();
  rememberCurrentReport(null);
  const versions = {
    ...buildQueryContext(
      queryContext.originalQuery,
      queryContext.rewrittenQuery,
      normalizedPrompt,
    ),
    workflowMode: queryContext.workflowMode || "dynamic",
    stockSymbol: queryContext.stockSymbol || "",
    stockName: queryContext.stockName || "",
    stockBoard: queryContext.stockBoard || "",
  };
  setLiveSession({
    prompt: normalizedPrompt,
    phase: "planning",
    ...versions,
  });
  navigate("war");
  if (switchedToLive) {
    refreshServiceStatus().finally(() => {
      renderTopbar();
      renderStatusbar();
    });
  }
  startResearchRun(normalizedPrompt, versions)
    .then(({ runId }) => {
      setLiveSession({ runId, connectionIssue: false });
      livePlanningSource = openResearchRunStream(runId, {
        onState: (state) => {
          setLiveSession({
            researchState: state,
            connectionIssue: false,
            error: state.error,
          });
          if (state.status === "failed") {
            livePlanningSource = null;
            setLiveSession({ phase: "failed" });
            if (currentRoute === "war") renderPage();
            return;
          }
          if (state.status === "plan_ready" && state.dag) {
            livePlanningSource = null;
            const plan = mapPlan(state.dag);
            setLiveSession({
              taskId: runId,
              plan,
              phase: plan && plan.needsClarification ? "clarification" : "planned",
              error: null,
            });
            navigate(plan && plan.needsClarification ? "clarify" : "war");
            return;
          }
          if (currentRoute === "war") renderPage();
        },
        onDisconnect: () => {
          setLiveSession({ connectionIssue: true });
          if (currentRoute === "war") renderPage();
        },
        onRecovering: () => {
          setLiveSession({ connectionIssue: true });
          if (currentRoute === "war") renderPage();
        },
        onRecoveryError: () => {
          setLiveSession({ connectionIssue: true });
          if (currentRoute === "war") renderPage();
        },
      });
    })
    .catch((error) => {
      const message = error?.message || "研究服务暂时无法创建任务，请稍后重试。";
      setLiveSession({ phase: "failed", error: message });
      navigate("war");
      toast(`规划失败：${message}`);
    });
}

// ---------------------------------------------------------------------------
// mode (demo | live) — live is the default product workflow. Demo mode is a
// labelled local walkthrough for sales demos and offline product review.
// ---------------------------------------------------------------------------
let liveStatus = { online: false, healthy: false, pandadata: null };

function setMode(mode) {
  if (store.state.mode === mode) return;
  store.set({ mode });
  toast(mode === "live" ? "已切换到实时研究" : "已切换到产品演示");
  refreshServiceStatus().finally(() => {
    renderTopbar();
    renderStatusbar();
    // Both modes start from the research hall so demos can show the full flow.
    navigate("hall");
  });
}

async function refreshServiceStatus() {
  if (!isLive()) {
    liveStatus = { online: false, healthy: false, pandadata: null };
    return liveStatus;
  }
  liveStatus = await connectivity();
  return liveStatus;
}

// Standard empty / error / loading states for live read-only pages.
function stateBox(kind, title, sub) {
  const box = el("div", "soon-wrap");
  const ico = kind === "error" ? "⚠" : kind === "empty" ? "🗂" : "⏳";
  box.appendChild(el("div", "sw-ico", ico));
  box.appendChild(el("h2", "", esc(title)));
  if (sub) box.appendChild(el("p", "", esc(sub)));
  return box;
}

// Render an async live page: show a loader, then swap in real content, or an
// error state (with the reason) if the backend is unreachable.
function renderLive(host, loader, builder) {
  host.innerHTML = "";
  host.appendChild(stateBox("loading", "正在读取研究结果…", "这里只展示已经完成的研究与可验证证据。"));
  loader()
    .then((data) => {
      host.innerHTML = "";
      host.appendChild(builder(data));
      highlightGlossaryScope(host);
    })
    .catch((err) => {
      host.innerHTML = "";
      const box = stateBox(
        "error",
        "研究服务暂时不可用",
        "当前无法读取研究结果，请稍后重试。",
      );
      const retry = el("button", "btn btn-primary", "重试");
      retry.addEventListener("click", () => renderLive(host, loader, builder));
      const row = el("div", "");
      row.style.cssText = "display:flex;gap:8px;justify-content:center;margin-top:10px";
      row.append(retry);
      box.appendChild(row);
      host.appendChild(box);
    });
  return host;
}

// ---------------------------------------------------------------------------
// tiny DOM helpers
// ---------------------------------------------------------------------------
const $ = (sel, root = document) => root.querySelector(sel);
const agentById = (id) => AGENTS.find((a) => a.id === id) || null;

function el(tag, cls, html) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (html != null) node.innerHTML = html;
  return node;
}

function esc(str) {
  return String(str ?? "").replace(/[&<>"']/g, (ch) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
  ));
}

function nowClock() {
  return new Date().toLocaleTimeString("zh-CN", { hour12: false });
}

// Product page heading. The numeric argument is kept for older call sites.
function screenTitle(num, name, sub) {
  const box = el("div", "screen-title");
  box.innerHTML = `<h1>${esc(name)}</h1>` +
    (sub ? `<p>${esc(sub)}</p>` : "");
  return box;
}

// ---------------------------------------------------------------------------
// pixel sprite avatars — drawn from /pixel/<sheet>/atlas.png (frame 0)
// ---------------------------------------------------------------------------
const SPRITE_BASE = "/pixel";
const SPRITE_MAP = {
  manager: "white-beard-businessman",
  macro: "gray-mustache-businessman",
  research: "white-hair-glasses",
  quant: "bald-round-glasses",
  risk: "balding-square-glasses",
  report: "bald-glasses",
  user: "black-hair-businessman",
};
const FRAME = 256; // avatar canvas resolution (a single grid cell is scaled into this)
// Every character atlas is a 6-column x 3-row grid. Rows are view directions,
// columns 0-3 are the walk cycle and 4-5 are the idle (breathing) pair.
const SHEET_COLS = 6;
const SHEET_ROWS = 3;
const ROW_FRONT = 0; // facing the viewer (moving down / toward camera)
const ROW_BACK = 1; // facing away (moving up / toward monitors — used when seated)
const ROW_SIDE = 2; // facing LEFT (moving left; horizontally flipped for right)
const WALK_COLS = [0, 1, 2, 3]; // contact, passing, contact, passing
const IDLE_COLS = [4, 5]; // stand, slight breathing dip
const SPRITE_SHEETS = new Set(Object.values(SPRITE_MAP)); // only these atlases exist
const spriteCache = new Map(); // sheet -> entry (aliases into imageCache)

// scene layers (top-down office + separate chair layer for the sitting effect)
const BG_URL = `${SPRITE_BASE}/backgroud.png`;
const CHAIR_URL = `${SPRITE_BASE}/chairs1.png`;
const CHAIR_COLS = 8; // chairs1.png is a horizontal strip of 8 back-view chairs
const BG_RATIO = 1586 / 992; // backgroud.png native aspect (scenes match it to avoid distortion)
// Non-transparent content box of each chair, measured within its cell (cell = 271.5px wide,
// 724px tall). Chairs are drawn from this crop so their base lands exactly on the seat point.
const CHAIR_BOX = [
  [72, 248, 252, 440], [65, 248, 246, 440], [59, 248, 240, 440], [53, 249, 234, 440],
  [51, 249, 222, 440], [44, 249, 222, 440], [39, 249, 218, 440], [33, 249, 214, 440],
];
// A character cell is mostly padding: the sprite's feet sit at ~0.89 of the cell height.
const CELL_FEET = 0.89;
// Six desk seats as fractions of the background image, so they scale with any canvas size.
// A seat's (fx,fy) marks where the chair base rests on the floor; `chair` picks a colour.
const SEATS = {
  manager:  { fx: 0.243, fy: 0.410, chair: 5 }, // top-left desk (brown)
  macro:    { fx: 0.196, fy: 0.640, chair: 2 }, // mid-left desk (navy)
  research: { fx: 0.240, fy: 0.870, chair: 4 }, // bottom-left desk (blue)
  quant:    { fx: 0.744, fy: 0.400, chair: 6 }, // top-right desk (grey)
  risk:     { fx: 0.798, fy: 0.640, chair: 1 }, // mid-right desk (charcoal)
  report:   { fx: 0.738, fy: 0.870, chair: 3 }, // bottom-right desk (purple)
};
const TABLE_CENTER = { fx: 0.5, fy: 0.565 }; // round meeting table (roundtable/visit gather point)
// Seated-sprite tuning (fractions of the scene width) — calibrated against the screenshot.
const CHAIR_W_FRAC = 0.062; // chair display width
const SEAT_PERSON_SCALE = 1.7; // person cell size relative to chair width
const SEAT_PERSON_LIFT = 0.62; // how far the seated person's feet-line rides above the chair base
const CHAIR_DROP_FRAC = 0.018; // chair base sits this far (of scene width) below the seat anchor

// Generic image cache shared by sprite atlases and scene layers.
const imageCache = new Map(); // url -> { img, ready, error, waiters }
function loadImage(url) {
  if (imageCache.has(url)) return imageCache.get(url);
  const img = new Image();
  const entry = { img, ready: false, error: false, waiters: [] };
  img.onload = () => {
    entry.ready = true;
    entry.waiters.splice(0).forEach((cb) => cb());
  };
  img.onerror = () => {
    entry.error = true;
    entry.waiters.splice(0).forEach((cb) => cb());
  };
  img.src = url;
  imageCache.set(url, entry);
  return entry;
}

function loadSprite(sheet) {
  const entry = loadImage(`${SPRITE_BASE}/${sheet}/atlas.png`);
  spriteCache.set(sheet, entry);
  return entry;
}

// Draw one grid cell (col,row) of a character atlas into the given dest rect.
function drawCell(ctx, entry, col, row, dx, dy, dw, dh) {
  const cw = entry.img.width / SHEET_COLS;
  const ch = entry.img.height / SHEET_ROWS;
  ctx.drawImage(entry.img, col * cw, row * ch, cw, ch, dx, dy, dw, dh);
}

// Pick the view row + horizontal flip from a movement vector.
function facingFrom(dx, dy) {
  if (Math.abs(dx) >= Math.abs(dy)) {
    return { row: ROW_SIDE, flip: dx > 0 }; // side art faces left; flip for right
  }
  return { row: dy < 0 ? ROW_BACK : ROW_FRONT, flip: false };
}

// Draw a character cell so it is centred on (cx) with the sprite's feet at (feetY),
// honouring the CELL_FEET padding and an optional horizontal flip (mirrored about cx).
function drawSpriteCell(ctx, entry, col, row, flip, cx, feetY, size) {
  const dx = cx - size / 2;
  const dy = feetY - CELL_FEET * size;
  if (flip) {
    ctx.save();
    ctx.translate(cx * 2, 0);
    ctx.scale(-1, 1);
    drawCell(ctx, entry, col, row, dx, dy, size, size);
    ctx.restore();
  } else {
    drawCell(ctx, entry, col, row, dx, dy, size, size);
  }
}

// Draw the office background scaled to fill (W,H). Scene sizes match BG_RATIO so no stretch.
function drawBackground(ctx, W, H) {
  const e = imageCache.get(BG_URL);
  if (e && e.ready) {
    ctx.drawImage(e.img, 0, 0, e.img.width, e.img.height, 0, 0, W, H);
  } else {
    ctx.fillStyle = "#f5f5f2";
    ctx.fillRect(0, 0, W, H);
  }
}

// Draw one back-view chair from its content crop, base resting at (sx,sy).
function drawChair(ctx, idx, sx, sy, cw) {
  const e = imageCache.get(CHAIR_URL);
  if (!e || !e.ready) return;
  const cellW = e.img.width / CHAIR_COLS;
  const [x0, y0, x1, y1] = CHAIR_BOX[idx % CHAIR_COLS];
  const sw = x1 - x0, sh = y1 - y0;
  const dw = cw, dh = cw * (sh / sw);
  ctx.drawImage(e.img, idx * cellW + x0, y0, sw, sh, sx - dw / 2, sy - dh, dw, dh);
}

// Draw a seat's chair as persistent furniture. `sy` is the seat anchor on the
// floor; the chair base drops slightly below it so it reads as standing in front
// of the desk. Safe to call whether or not anyone is sitting there.
function drawSeatChair(ctx, chairIdx, sx, sy, W) {
  drawChair(ctx, chairIdx || 0, sx, sy + W * CHAIR_DROP_FRAC, W * CHAIR_W_FRAC);
}

// Draw only the seated back-view person (no chair) anchored at seat point (sx,sy).
function drawSeatedPerson(ctx, sheet, sx, sy, W) {
  const chairW = W * CHAIR_W_FRAC;
  const personSize = chairW * SEAT_PERSON_SCALE;
  const feetY = sy - chairW * SEAT_PERSON_LIFT;
  const entry = spriteCache.get(sheet);
  if (entry && entry.ready) {
    drawSpriteCell(ctx, entry, IDLE_COLS[0], ROW_BACK, false, sx, feetY, personSize);
  }
}

// Draw a seated agent at a seat point (sx,sy = seat anchor on the floor): the
// back-view sprite is painted first, then the chair on top so the backrest hides
// the lower body. The chair is always present via drawSeatChair even when empty.
function drawSeated(ctx, sheet, sx, sy, W, chairIdx) {
  drawSeatedPerson(ctx, sheet, sx, sy, W);
  drawSeatChair(ctx, chairIdx, sx, sy, W);
}

// Returns a wrapper element containing a crisp pixel-art avatar canvas.
function avatar(agentOrSheet, sizePx = 40, wrapCls = "pix-ava") {
  const sheet = SPRITE_MAP[agentOrSheet] || agentOrSheet;
  const wrap = el("span", wrapCls);
  wrap.style.width = `${sizePx}px`;
  wrap.style.height = `${sizePx}px`;
  wrap.style.display = "inline-block";
  const canvas = el("canvas");
  canvas.width = FRAME;
  canvas.height = FRAME;
  // Size the canvas to fill the wrapper regardless of wrapper class, so small
  // avatars (team row / contrib cards) don't show only the sprite's top-left.
  canvas.style.width = "100%";
  canvas.style.height = "100%";
  canvas.style.display = "block";
  canvas.style.imageRendering = "pixelated";
  wrap.appendChild(canvas);
  const ctx = canvas.getContext("2d");
  const paint = () => {
    const entry = spriteCache.get(sheet);
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, FRAME, FRAME);
    if (entry && entry.ready) {
      // front-facing idle (standing) frame, scaled to fill the avatar canvas
      drawCell(ctx, entry, IDLE_COLS[0], ROW_FRONT, 0, 0, FRAME, FRAME);
    } else {
      // graceful fallback: solid pixel block while the atlas loads / on error
      ctx.fillStyle = "#d9d9d3";
      ctx.fillRect(0, 0, FRAME, FRAME);
    }
  };
  const entry = SPRITE_SHEETS.has(sheet) ? loadSprite(sheet) : null;
  paint();
  if (entry && !entry.ready) entry.waiters.push(paint);
  return wrap;
}

// ---------------------------------------------------------------------------
// nav definition
// ---------------------------------------------------------------------------
const NAV = [
  { route: "hall", ico: "🏛", label: "投研大厅" },
  { route: "war", ico: "🛰", label: "多 Agent 作战室" },
  { route: "experts", ico: "👥", label: "专家中心" },
  { route: "reports", ico: "📑", label: "研究报告" },
  { route: "stock-library", ico: "▦", label: "股票库" },
  { route: "stocks", ico: "📈", label: "股票行情" },
  { route: "glossary", ico: "📚", label: "投研知识库" },
  { route: "profile", ico: "🪪", label: "用户画像" },
  { route: "skills", ico: "🧩", label: "研究能力" },
];

let currentRoute = "stock-library";
let routeParam = null;
const SIDEBAR_COLLAPSED_KEY = "alphabit-coach.sidebar-collapsed";
let sidebarCollapsed = false;
try {
  sidebarCollapsed = window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true";
} catch (_) {
  sidebarCollapsed = false;
}
const CURRENT_REPORT_KEY = "alphabit-coach.current-report-id";
let currentReportId = null;
try {
  currentReportId = window.sessionStorage.getItem(CURRENT_REPORT_KEY);
} catch (_) {
  currentReportId = null;
}
function rememberCurrentReport(reportId) {
  currentReportId = reportId || null;
  try {
    if (currentReportId) window.sessionStorage.setItem(CURRENT_REPORT_KEY, currentReportId);
    else window.sessionStorage.removeItem(CURRENT_REPORT_KEY);
  } catch (_) {
    // The current page still works when browser storage is unavailable.
  }
}
// teardown hook for pages that own timers / animation frames (war room, live scenes)
let activeTeardown = null;
function registerTeardown(fn) { activeTeardown = fn; }

// ---------------------------------------------------------------------------
// shell — sidebar / topbar / statusbar
// ---------------------------------------------------------------------------
function renderSidebar() {
  const side = $("#sidebar");
  side.innerHTML = "";
  side.className = `sidebar${sidebarCollapsed ? " collapsed" : ""}`;

  const sidebarHead = el("div", "sidebar-head");
  const brand = el("button", "brand");
  brand.appendChild(el("span", "brand-mark", "◆"));
  brand.appendChild(el("span", "brand-copy", "<strong>AlphaBit Coach</strong><small>AI 投资研究操作系统</small>"));
  brand.addEventListener("click", () => navigate("hall"));

  const collapseButton = el(
    "button",
    "sidebar-collapse",
    sidebarCollapsed ? "»" : "«",
  );
  collapseButton.type = "button";
  collapseButton.title = sidebarCollapsed ? "展开侧边栏" : "收起侧边栏";
  collapseButton.setAttribute("aria-label", collapseButton.title);
  collapseButton.setAttribute("aria-expanded", String(!sidebarCollapsed));
  collapseButton.addEventListener("click", () => {
    sidebarCollapsed = !sidebarCollapsed;
    try {
      window.localStorage.setItem(
        SIDEBAR_COLLAPSED_KEY,
        String(sidebarCollapsed),
      );
    } catch (_) {
      // The current layout still updates when storage is unavailable.
    }
    renderSidebar();
  });
  sidebarHead.append(brand, collapseButton);
  side.appendChild(sidebarHead);

  const nav = el("nav", "nav");
  NAV.forEach((item) => {
    if (item.sep) {
      nav.appendChild(el("div", "nav-sep"));
      return;
    }
    const active = item.route === currentRoute;
    const btn = el(
      "button",
      `nav-item${active ? " active" : ""}`,
    );
    btn.title = item.label;
    btn.setAttribute("aria-label", item.label);
    btn.appendChild(el("span", "nav-ico", item.ico));
    btn.appendChild(el("span", "nav-label", esc(item.label)));
    btn.addEventListener("click", () => navigate(item.route));
    nav.appendChild(btn);
  });
  side.appendChild(nav);

  side.appendChild(el("div", "sidebar-foot", `AlphaBit Coach v0.4${isLive() ? "" : " · 产品演示"}`));
}

function renderTopbar() {
  const bar = $("#topbar");
  bar.innerHTML = "";
  const stockSurface = currentRoute === "stock-library" || currentRoute === "stocks";

  if (stockSurface) {
    bar.appendChild(
      el(
        "span",
        "pill stock-surface-label",
        currentRoute === "stock-library" ? "股票库 · 38 个标的" : "股票行情 · K 线",
      ),
    );
  } else if (isLive()) {
    const ok = liveStatus.healthy;
    const status = el(
      "span",
      "pill",
      `<span class="dot ${ok ? "ok" : "warn"}"></span>研究服务：<strong style="color:var(--${ok ? "green" : "yellow"})">${ok ? "已连接" : "连接中/离线"}</strong>`,
    );
    const pd = liveStatus.pandadata || {};
    const pdReady = pd.configured || pd.ready || pd.status === "ok";
    const data = el(
      "span",
      "pill",
      `专业数据服务：${pdReady ? '已就绪 <span class="dot ok"></span>' : '尚未就绪 <span class="dot warn"></span>'}`,
    );
    bar.append(status, data);
  } else {
    bar.appendChild(el("span", "pill", '<span class="dot warn"></span>产品演示：本地示例，不调用模型或数据源'));
  }

  bar.appendChild(el("div", "topbar-spacer"));

  if (!stockSurface) {
    const live = isLive();
    const modeBtn = el("button", "pill", live ? "查看产品演示" : "切换到实时研究");
    modeBtn.title = live
      ? "使用本地示例演示完整产品流程"
      : "返回真实研究流程";
    modeBtn.addEventListener("click", () => setMode(live ? "demo" : "live"));
    bar.append(modeBtn);

    const history = el("button", "pill", "🕘 历史记录");
    history.addEventListener("click", () => navigate("tasks"));
    bar.append(history);
  }

  const avaBtn = el("button", "avatar-btn");
  avaBtn.appendChild(avatar("user", 34, "pix-ava"));
  avaBtn.addEventListener("click", () => navigate("profile"));
  bar.appendChild(avaBtn);
}

function renderStatusbar() {
  const sb = $("#statusbar");
  sb.innerHTML = "";
  sb.appendChild(el("span", "sb-item", "AI 投研团队 · 证据边界清晰 · 仅供研究参考"));
  sb.appendChild(el("span", "spacer"));
  sb.appendChild(el("span", "sb-item sb-slogan", nowClock()));
}

// ---------------------------------------------------------------------------
// toast
// ---------------------------------------------------------------------------
function toast(message) {
  const root = $("#toastRoot");
  const node = el("div", "toast", esc(message));
  root.appendChild(node);
  setTimeout(() => {
    node.style.opacity = "0";
    node.style.transition = "opacity 0.3s";
    setTimeout(() => node.remove(), 320);
  }, 2200);
}

// ---------------------------------------------------------------------------
// canvas line chart (report trend)
// ---------------------------------------------------------------------------
function drawLineChart(canvas, trend) {
  const dpr = window.devicePixelRatio || 1;
  const cssW = canvas.clientWidth || 360;
  const cssH = 210;
  canvas.width = cssW * dpr;
  canvas.height = cssH * dpr;
  canvas.style.height = `${cssH}px`;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, cssW, cssH);

  const padL = 40, padR = 12, padT = 14, padB = 26;
  const plotW = cssW - padL - padR;
  const plotH = cssH - padT - padB;
  const all = trend.series.flatMap((s) => s.data);
  const maxV = Math.max(...all, 10);
  const minV = Math.min(...all, 0);
  const range = maxV - minV || 1;
  const n = trend.labels.length;
  const xAt = (i) => padL + (n <= 1 ? 0 : (plotW * i) / (n - 1));
  const yAt = (v) => padT + plotH - ((v - minV) / range) * plotH;

  // gridlines + y labels
  ctx.strokeStyle = "#e9e9e5";
  ctx.fillStyle = "#9f9f9a";
  ctx.font = "10px system-ui, sans-serif";
  ctx.textAlign = "right";
  const steps = 4;
  for (let i = 0; i <= steps; i++) {
    const v = minV + (range * i) / steps;
    const y = yAt(v);
    ctx.beginPath();
    ctx.moveTo(padL, y);
    ctx.lineTo(cssW - padR, y);
    ctx.stroke();
    ctx.fillText(`${Math.round(v)}%`, padL - 6, y + 3);
  }

  // x labels
  ctx.textAlign = "center";
  trend.labels.forEach((lb, i) => ctx.fillText(lb, xAt(i), cssH - 8));

  // series
  trend.series.forEach((s) => {
    ctx.strokeStyle = s.color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    s.data.forEach((v, i) => {
      const x = xAt(i), y = yAt(v);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.fillStyle = s.color;
    s.data.forEach((v, i) => {
      ctx.beginPath();
      ctx.arc(xAt(i), yAt(v), 3, 0, Math.PI * 2);
      ctx.fill();
    });
  });
}

// ---------------------------------------------------------------------------
// canvas radar chart (capability radar)
// ---------------------------------------------------------------------------
function drawRadar(canvas, radar, size = 220) {
  const dpr = window.devicePixelRatio || 1;
  canvas.width = size * dpr;
  canvas.height = size * dpr;
  canvas.style.width = `${size}px`;
  canvas.style.height = `${size}px`;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, size, size);

  const labels = radar.labels || [];
  const vals = radar.values || [];
  const n = labels.length;
  if (!n) return;
  const cx = size / 2;
  const cy = size / 2;
  const R = size / 2 - 30;
  const ang = (i) => -Math.PI / 2 + (i * 2 * Math.PI) / n;
  const maxV = 100;

  // concentric rings
  ctx.strokeStyle = "#e9e9e5";
  ctx.lineWidth = 1;
  for (let r = 1; r <= 4; r++) {
    const rr = (R * r) / 4;
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      const a = ang(i);
      const x = cx + rr * Math.cos(a);
      const y = cy + rr * Math.sin(a);
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    }
    ctx.closePath();
    ctx.stroke();
  }

  // spokes + axis labels
  ctx.fillStyle = "#6e6e6e";
  ctx.font = "10px system-ui, sans-serif";
  ctx.textAlign = "center";
  for (let i = 0; i < n; i++) {
    const a = ang(i);
    ctx.strokeStyle = "#e9e9e5";
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + R * Math.cos(a), cy + R * Math.sin(a));
    ctx.stroke();
    const lx = cx + (R + 15) * Math.cos(a);
    const ly = cy + (R + 15) * Math.sin(a);
    ctx.fillText(labels[i], lx, ly + 3);
  }

  // value polygon
  ctx.beginPath();
  for (let i = 0; i < n; i++) {
    const a = ang(i);
    const rr = (R * Math.min(vals[i] ?? 0, maxV)) / maxV;
    const x = cx + rr * Math.cos(a);
    const y = cy + rr * Math.sin(a);
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  }
  ctx.closePath();
  ctx.fillStyle = "rgba(17, 17, 17, 0.08)";
  ctx.fill();
  ctx.strokeStyle = "#111111";
  ctx.lineWidth = 2;
  ctx.stroke();
  ctx.fillStyle = "#111111";
  for (let i = 0; i < n; i++) {
    const a = ang(i);
    const rr = (R * Math.min(vals[i] ?? 0, maxV)) / maxV;
    ctx.beginPath();
    ctx.arc(cx + rr * Math.cos(a), cy + rr * Math.sin(a), 2.6, 0, Math.PI * 2);
    ctx.fill();
  }
}

// ---------------------------------------------------------------------------
// router
// ---------------------------------------------------------------------------
function navigate(route, param = null) {
  currentRoute = route;
  routeParam = param;
  if (!(route === "reports" && param) && globalThis.AlphaGlossary?.setResearchEntries) {
    globalThis.AlphaGlossary.setResearchEntries([]);
  }
  renderTopbar();
  renderSidebar();
  renderPage();
  $("#page").scrollTop = 0;
}

function renderPage() {
  if (activeTeardown) { try { activeTeardown(); } catch (_) {} activeTeardown = null; }
  const page = $("#page");
  page.innerHTML = "";
  const live = isLive();
  switch (currentRoute) {
    case "stock-library": {
      const libraryHost = el("div");
      page.appendChild(libraryHost);
      registerTeardown(
        mountStockLibraryPage(libraryHost, {
          notify: toast,
          onOpenChart: (stock) => navigate("stocks", stock),
        }),
      );
      break;
    }
    case "stocks": {
      const stockHost = el("div");
      page.appendChild(stockHost);
      registerTeardown(
        mountStockChartPage(stockHost, {
          forceDemo: !live,
          initialStock: routeParam,
          notify: toast,
          onChooseStock: () => navigate("stock-library"),
          onAnalyzeStock: (stock) =>
            beginLiveResearch(
              buildStockResearchPrompt(stock),
              buildStockWorkflowContext(stock),
            ),
        }),
      );
      break;
    }
    case "reports":
      if (live) page.appendChild(routeParam ? pageReportDetailLive(routeParam) : pageReportListLive());
      else if (routeParam) page.appendChild(pageReportDetail(routeParam));
      else page.appendChild(pageReportList());
      break;
    case "hall":
      page.appendChild(live ? pageHallLive() : pageHall());
      break;
    case "clarify":
      page.appendChild(live ? pageClarifyLive() : pageClarify());
      break;
    case "war":
      page.appendChild(live ? pageWarRoomLive() : pageWarRoom());
      break;
    case "experts":
      page.appendChild(live ? pageExpertsLive() : pageExperts());
      break;
    case "tasks":
      page.appendChild(live ? pageTasksLive() : pageTasks());
      break;
    case "skills":
      page.appendChild(live ? pageSkillsLive() : pageSkills());
      break;
    case "glossary":
      page.appendChild(buildOfficeGlossaryPage());
      break;
    case "profile":
      mountProfilePage(page, toast);
      break;
    default:
      navigate("hall");
  }
  requestAnimationFrame(() => highlightGlossaryScope(page));
}

// ---------------------------------------------------------------------------
// page: report list
// ---------------------------------------------------------------------------
function pageReportList() {
  if (REPORTS.length) return pageReportDetail(REPORTS[0].id);
  const wrap = el("div", "panel");
  wrap.appendChild(stateBox("empty", "暂无当前研究报告", "完成一次研究后，报告会在这里直接打开。"));
  return wrap;
}

// ---------------------------------------------------------------------------
// page: report detail + follow-up (界面 06)
// ---------------------------------------------------------------------------
function pageReportDetail(reportId) {
  const report = REPORTS.find((r) => r.id === reportId) || REPORTS[0];
  const researchReport = buildDemoResearchReport(report);
  const layout = el("div", "report-layout");
  const main = buildReportMainLive(researchReport);
  layout.appendChild(main);
  // demo coach sidebar: locally labeled sample data, no credentials required
  const coach = buildCoachSidebar({
    demo: true,
    seedMessages: DEMO_COACH.seedMessages || [],
    sectionContexts: main.reportNavigation || [],
    loadGuide: () => Promise.resolve(DEMO_COACH.guide),
    ask: (question, quoted) => new Promise((resolve) => {
      setTimeout(() => resolve({ ...DEMO_COACH.reply, quoted_text: quoted || null }), 600);
    }),
    evidence: (question) => new Promise((resolve) => {
      setTimeout(() => resolve({
        text: matchReply(report, question),
        evidence: [],
        created_at: "",
      }), 600);
    }),
    onCollapseChange: (c) => layout.classList.toggle("coach-collapsed", c),
  });
  layout.appendChild(coach.root);
  const reading = wireReportReading(main, coach);
  const quoting = attachSelectionQuoting(main, (text) => coach.setQuote(text));
  registerTeardown(() => {
    reading.destroy();
    quoting.destroy();
  });
  return layout;
}

const DEMO_REPORT_PROFILES = {
  "r-ne-20240430": {
    intent: "industry_research",
    headline: "新能源行业仍处在结构性成长阶段，但分化会比总量增长更重要。",
    explanation: "演示证据显示，储能和海风同时具备需求增速、政策可见度和盈利改善线索；光伏一体化处在出清左侧，结论强度低于储能和海风。",
    confidence: "medium",
    stance: "cautiously_positive",
    metrics: [
      {
        metric: "revenue_yoy",
        label: "行业收入同比增速",
        display_value: "+28.6%",
        subject: "2023-2026E 示例复合增速",
        formula: "（期末行业收入 / 期初行业收入）^(1 / 年数) - 1",
        explanation: "储能与海风贡献主要增量，代表行业需求仍处扩张阶段。",
      },
      {
        metric: "gross_margin",
        label: "重点赛道毛利率中枢",
        display_value: "21.4%",
        subject: "2024E 示例均值",
        formula: "重点公司毛利额合计 / 重点公司收入合计",
        explanation: "储能系统毛利率企稳，光伏环节仍受价格竞争影响。",
      },
      {
        metric: "operating_cash_flow_to_net_profit",
        label: "现金流利润覆盖倍数",
        display_value: "1.12x",
        subject: "龙头样本 2024E 示例",
        formula: "经营活动现金流净额 / 净利润",
        explanation: "龙头样本现金流覆盖利润，盈利质量暂未明显恶化。",
      },
      {
        metric: "asset_liability_ratio",
        label: "资产负债率",
        display_value: "58.3%",
        subject: "重点公司样本中位数",
        formula: "总负债 / 总资产",
        explanation: "重资产扩张阶段杠杆处于中等水平，需继续观察融资成本。",
      },
    ],
    evidence: [
      "储能系统 2024E 装机增速示例值为 +120%，在细分赛道中最高。",
      "海上风电吊装增速示例值为 +65%，受竞配项目开工节奏支撑。",
      "光伏一体化评分 85 分，反映成本曲线优势但仍受产能出清影响。",
      "压力测试显示极端情景最大回撤约 12%，主要来自价格战与海外政策扰动。",
    ],
    risks: [
      "电池和光伏环节仍有产能过剩风险，价格竞争可能压低毛利率。",
      "海外贸易政策变化可能改变出口订单的盈利和交付节奏。",
      "利率若重新上行，成长赛道估值中枢可能被压缩。",
    ],
    limitations: [
      "演示数据未接入实时订单、排产和海外关税数据。",
      "细分赛道评分来自本地示例模型，不能替代真实样本验证。",
      "行业景气指数为演示口径，不应被解释为投资信号。",
    ],
    next: [
      "用真实装机、招标价格和上市公司订单验证储能景气持续性。",
      "按细分赛道拆分收入、毛利率和现金流，排除总量数据掩盖的分化。",
      "补充海外政策情景，对出口链盈利做敏感性分析。",
    ],
    sources: [
      { name: "本地演示行业数据包", method: "demo_industry_panel", missing_status: "available", period: "2022-2025E", row_count: 128 },
      { name: "公开披露摘录样本", method: "demo_company_filings", missing_status: "available", latest_report_period: "2024Q1", row_count: 36 },
      { name: "本地压力测试脚本", method: "demo_stress_scenario", missing_status: "available", period: "极端情景", row_count: 4 },
    ],
  },
  default: {
    intent: "company_research",
    headline: "公司盈利质量仍处于较强区间，短期关键变量是需求和价格信号能否稳定。",
    explanation: "演示证据显示，公司核心盈利能力、现金流和估值分位均具备研究价值；但需求恢复和渠道价格仍是需要跟踪的主要不确定性。",
    confidence: "medium",
    stance: "mixed",
    metrics: [
      {
        metric: "revenue_yoy",
        label: "营业收入同比增长率",
        display_value: "+16.8%",
        subject: "2024E 示例",
        formula: "（本期营业收入 / 上年同期营业收入 - 1）× 100%",
        explanation: "收入仍保持增长，但需要结合渠道库存验证持续性。",
      },
      {
        metric: "net_profit_yoy",
        label: "净利润同比增长率",
        display_value: "+18.4%",
        subject: "2024E 示例",
        formula: "（本期净利润 / 上年同期净利润 - 1）× 100%",
        explanation: "利润增速略高于收入，说明盈利效率未明显弱化。",
      },
      {
        metric: "gross_margin",
        label: "毛利率",
        display_value: "91.6%",
        subject: "2024E 示例",
        formula: "（营业收入 - 营业成本）/ 营业收入",
        explanation: "高毛利率体现品牌和产品结构优势，但需要观察批价变化。",
      },
      {
        metric: "operating_cash_flow_to_net_profit",
        label: "经营现金流与净利润比",
        display_value: "1.18x",
        subject: "近三年示例均值",
        formula: "经营活动现金流净额 / 净利润",
        explanation: "现金流覆盖利润，说明账面利润质量较好。",
      },
      {
        metric: "asset_liability_ratio",
        label: "资产负债率",
        display_value: "14.7%",
        subject: "2024E 示例",
        formula: "总负债 / 总资产",
        explanation: "杠杆水平较低，财务压力相对可控。",
      },
    ],
    evidence: [
      "近三年示例 ROE 维持在 30% 以上，显著高于行业均值。",
      "经营现金流与净利润比为 1.18x，利润现金含量较好。",
      "估值分位示例值为近五年 22%，处于历史中枢下沿。",
      "风险扫描把批价波动、需求复苏和消费税预期列为主要跟踪项。",
    ],
    risks: [
      "若批价再次下探，渠道信心和估值修复节奏会先受影响。",
      "需求复苏不及预期会削弱收入增长的可持续性。",
      "消费税改革预期可能改变市场对利润率的折现方式。",
    ],
    limitations: [
      "演示数据未接入实时批价和渠道库存。",
      "估值分位为本地示例口径，真实研究需重新计算样本区间。",
      "未纳入个人风险承受能力和持仓约束。",
    ],
    next: [
      "补充真实批价、渠道库存和动销数据，验证需求恢复强度。",
      "用最近五年估值分位和自由现金流收益率交叉检查安全边际。",
      "做消费税改革情景测算，观察净利率和估值中枢变化。",
    ],
    sources: [
      { name: "本地演示财务数据包", method: "demo_financial_panel", missing_status: "available", latest_report_period: "2024E", row_count: 24 },
      { name: "公开披露摘录样本", method: "demo_company_filings", missing_status: "available", latest_report_period: "2024Q1", row_count: 18 },
      { name: "本地估值分位样本", method: "demo_valuation_percentile", missing_status: "available", period: "2019-2024", row_count: 260 },
    ],
  },
};

function demoProfileFor(report) {
  return DEMO_REPORT_PROFILES[report.id] || DEMO_REPORT_PROFILES.default;
}

function demoSourceStep(steps, agent) {
  return steps.find((step) => step.agent === agent)?.id || steps[0]?.id || "";
}

function demoItems(items, type, sourceSteps) {
  return (items || []).map((text) => ({
    text,
    evidence_type: type,
    source_steps: sourceSteps.filter(Boolean),
  }));
}

function buildDemoResearchReport(report) {
  const selectedAgents = (report.team || []).filter((id) => id !== "manager");
  const steps = selectedAgents.map((agent, index) => ({
    id: `${agent}_demo_${index + 1}`,
    agent,
    objective: (report.contributions?.[agent] || []).join("；")
      || "完成本次分配的专业研究问题",
    expected_output: agent === "report"
      ? "整合本次专家证据形成统一报告"
      : "形成带证据边界的阶段性研究结果",
    depends_on: agent === "report"
      ? selectedAgents
        .filter((id) => id !== "report")
        .map((id) => `${id}_demo_${selectedAgents.indexOf(id) + 1}`)
      : [],
  }));
  const profile = demoProfileFor(report);
  const macroStep = demoSourceStep(steps, "macro");
  const researchStep = demoSourceStep(steps, "research");
  const quantStep = demoSourceStep(steps, "quant");
  const riskStep = demoSourceStep(steps, "risk");
  const reportStep = demoSourceStep(steps, "report");
  const primarySteps = [macroStep, researchStep, quantStep].filter(Boolean);
  const riskSteps = [riskStep || researchStep].filter(Boolean);
  const sourceResults = Object.fromEntries(steps.map((step) => [
    step.id,
    {
      agent: step.agent,
      status: "completed",
      summary: demoAgentSummary(step.agent, report, profile),
      assumptions: demoAgentAssumptions(step.agent),
      risks: step.agent === "risk"
        ? profile.risks.slice(0, 3)
        : [],
      limitations: demoAgentLimitations(step.agent, profile),
      recommendations: demoAgentRecommendations(step.agent, profile),
      data_sources: demoAgentSources(step.agent, profile.sources),
    },
  ]));
  const metricSource = researchStep || quantStep || steps.find((step) => step.agent !== "report")?.id || "";
  const findings = (report.body || []).map((item) => ({
    text: `${item.h}：${item.p}`,
    evidence_type: /风险/.test(item.h) ? "risk" : "judgment",
    source_steps: metricSource ? [metricSource] : [],
  }));
  const reportText = (report.body || [])
    .map((item) => `${item.h}\n${item.p}`)
    .join("\n\n");
  return {
    demo: true,
    title: report.title,
    created_at: report.doneAt,
    completeness: {
      planned_steps: steps.length,
      completed_steps: steps.length,
      failed_steps: 0,
      blocked_steps: 0,
      completion_ratio: steps.length ? 1 : 0,
    },
    task: {
      prompt: report.title,
      plan: {
        goal: report.title,
        intent: report.kind,
        selected_agents: selectedAgents.map((agent) => ({
          agent,
          reason: (report.contributions?.[agent] || []).join("；")
            || "参与本次研究。",
        })),
        steps,
      },
    },
    aggregation: {
      user_goal: report.title,
      completion_status: "completed",
      direct_answer: {
        headline: profile.headline,
        explanation: profile.explanation,
        confidence: profile.confidence,
        stance: profile.stance,
      },
      key_findings: [
        ...demoItems(profile.evidence.slice(0, 3), "judgment", primarySteps),
        ...findings.filter((item) => item.evidence_type !== "risk"),
      ],
      evidence_summary: demoItems(profile.evidence, "fact", primarySteps),
      risks: [
        ...demoItems(profile.risks, "risk", riskSteps),
        ...findings.filter((item) => item.evidence_type === "risk"),
      ],
      limitations: demoItems(profile.limitations, "limitation", riskSteps),
      next_research_steps: demoItems(profile.next, "research_action", [reportStep || riskStep || metricSource]),
      content_blocks: [
        {
          type: "metric_cards",
          source_steps: metricSource ? [metricSource] : [],
          data: {
            metrics: profile.metrics,
          },
        },
        {
          type: "report",
          source_steps: steps.map((step) => step.id),
          data: { content: reportText },
        },
      ],
      data_scope: profile.sources,
      technical_evidence: {
        conflicts: [
          "演示中的成长线索与风险线索同时存在：宏观和研究结果偏积极，风险结果要求验证价格战、需求和政策扰动。",
        ],
        source_results: sourceResults,
      },
      disclaimer: "产品演示使用本地示例数据，不构成投资建议。",
    },
  };
}

function buildReportMain(report) {
  const col = el("div", "glossary-scope");

  // toolbar
  const toolbar = el("div", "rpt-toolbar");
  const back = el("button", "btn-ghost", "‹ 返回报告列表");
  back.addEventListener("click", () => navigate("reports"));
  toolbar.appendChild(back);
  col.appendChild(toolbar);

  // hero: title + meta + team | score
  const heroPanel = el("div", "panel");
  const hero = el("div", "rpt-hero");
  const main = el("div", "rh-main");
  main.appendChild(el("span", "rh-ico", "📑"));
  const info = el("div");
  info.appendChild(el("h1", "", esc(report.title)));
  info.appendChild(el("div", "rpt-id", `
    <span>任务 ID：${esc(report.taskNo)}</span>
    <span>完成时间：${esc(report.doneAt)}</span>
    <span>目标周期：${esc(report.horizon)}</span>
    <span class="badge done"><span class="dot"></span>已完成</span>
  `));
  const team = el("div", "rpt-team");
  team.appendChild(el("span", "", "研究团队："));
  report.team.forEach((id) => {
    const a = agentById(id);
    if (!a) return;
    const tm = el("span", "tm");
    const ava = avatar(id, 30, "tm-ava");
    tm.appendChild(ava);
    tm.appendChild(el("span", "", esc(a.name)));
    team.appendChild(tm);
  });
  info.appendChild(team);
  main.appendChild(info);
  hero.appendChild(main);

  const dims = report.scoreDims || {};
  const score = el("div", "rpt-score", `
    <div class="rs-label">报告评分 <span>⌄</span></div>
    <div class="rs-big">${report.score}<small> / 100</small></div>
    <div class="rs-dims">
      ${Object.entries(dims).map(([k, v]) => `<span>${esc(k)} <b>${v}</b></span>`).join("")}
    </div>
  `);
  hero.appendChild(score);
  heroPanel.appendChild(hero);
  col.appendChild(heroPanel);

  // summary + charts row
  const row = el("div", "report-charts");
  row.style.marginTop = "14px";

  const summaryPanel = el("div", "panel rpt-summary");
  summaryPanel.appendChild(el("div", "panel-title", "报告摘要"));
  summaryPanel.appendChild(el("p", "", esc(report.summary)));
  const tags = el("div", "rpt-summary-tags");
  (report.tags || []).forEach((t) => tags.appendChild(el("span", "chip", esc(t))));
  summaryPanel.appendChild(tags);
  row.appendChild(summaryPanel);

  const chartPanel = el("div", "panel");
  chartPanel.appendChild(el("div", "panel-title", `核心观点与关键图表 <span class='title-extra'>查看完整报告 ›</span>`));
  // trend line chart
  chartPanel.appendChild(el("div", "", `<div style="color:var(--text-2);font-size:12px;margin-bottom:4px">${esc(report.trend.title)}</div>`));
  const chartBox = el("div", "chart-box");
  const canvas = el("canvas");
  chartBox.appendChild(canvas);
  const legend = el("div", "chart-legend");
  report.trend.series.forEach((s) => {
    legend.appendChild(el("span", "", `<i style="background:${s.color}"></i>${esc(s.name)}`));
  });
  chartBox.appendChild(legend);
  chartPanel.appendChild(chartBox);
  // track bars
  chartPanel.appendChild(el("div", "", `<div style="color:var(--text-2);font-size:12px;margin:14px 0 8px">细分赛道投资机会评分</div>`));
  const bars = el("div", "track-bars");
  const maxTrack = Math.max(...report.tracks.map((t) => t.v), 100);
  report.tracks.forEach((t) => {
    const color = t.v >= 80 ? "var(--green)" : t.v >= 70 ? "var(--cyan)" : "var(--blue)";
    const bar = el("div", "track-bar", `
      <span>${esc(t.name)}</span>
      <span class="tb-track"><i style="width:${(t.v / maxTrack) * 100}%;background:${color}"></i></span>
      <span class="tb-val" style="color:${color}">${t.v}</span>
    `);
    bars.appendChild(bar);
  });
  chartPanel.appendChild(bars);
  row.appendChild(chartPanel);
  col.appendChild(row);
  // draw chart after in DOM
  requestAnimationFrame(() => drawLineChart(canvas, report.trend));

  // key conclusions (kv cards)
  const kvPanel = el("div", "panel");
  kvPanel.style.marginTop = "14px";
  kvPanel.appendChild(el("div", "panel-title", "关键结论速览"));
  const kvCards = el("div", "kv-cards");
  (report.kv || []).forEach((k) => {
    const card = el("div", "kv-card", `
      <div class="kvc-label">${esc(k.label)}</div>
      <div class="kvc-val ${k.color === "green" ? "" : esc(k.color)}">${esc(k.value)}</div>
      <div style="color:var(--text-3);font-size:11px">${esc(k.sub)}</div>
    `);
    kvCards.appendChild(card);
  });
  kvPanel.appendChild(kvCards);
  col.appendChild(kvPanel);

  // team contribution review (contrib grid)
  const contribPanel = el("div", "panel");
  contribPanel.style.marginTop = "14px";
  contribPanel.appendChild(el("div", "panel-title", "团队贡献回顾"));
  const grid = el("div", "contrib-grid");
  report.team.forEach((id) => {
    const a = agentById(id);
    if (!a) return;
    const items = (report.contributions && report.contributions[id]) || a.contributions || [];
    const card = el("div", "contrib-card");
    card.appendChild(avatar(id, 40, "cc-ava"));
    card.appendChild(el("strong", "", esc(a.name)));
    card.appendChild(el("div", "", `<span style="color:var(--text-2)">${esc(a.duty)}</span>`));
    card.appendChild(el("ul", "", items.map((c) => `<li>· ${esc(c)}</li>`).join("")));
    grid.appendChild(card);
  });
  contribPanel.appendChild(grid);
  col.appendChild(contribPanel);

  // footer note
  col.appendChild(el("div", "rpt-note", "报告已完成，您可以继续追问或发起新的研究探索。"));

  return col;
}

// ---------------------------------------------------------------------------
// demo follow-up replies (侧边栏「只查证据」示例通道复用)
// ---------------------------------------------------------------------------
function matchReply(report, question) {
  const rules = report.followReplies || [];
  for (const rule of rules) {
    if (!rule.match || rule.match.length === 0) continue;
    if (rule.match.some((kw) => question.includes(kw))) return rule.reply;
  }
  const fallback = rules.find((r) => !r.match || r.match.length === 0);
  return fallback ? fallback.reply : "收到，我会基于报告的证据链继续分析。";
}

// ---------------------------------------------------------------------------
// canvas office scene — top-down pixel office with agents at their desks
// (static LIVE preview for the hall; the war room animates its own stage)
// ---------------------------------------------------------------------------
function drawOfficeScene(canvas, agents) {
  const dpr = window.devicePixelRatio || 1;
  const W = 720, H = Math.round(W / BG_RATIO);
  canvas.width = W * dpr;
  canvas.height = H * dpr;
  canvas.style.width = "100%";
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  // agents that own a desk seat, in seat order
  const seated = Object.keys(SEATS)
    .map((id) => ({ id, seat: SEATS[id], a: agents.find((x) => x.id === id) }))
    .filter((s) => s.a);

  const paint = () => {
    ctx.imageSmoothingEnabled = false;
    drawBackground(ctx, W, H);
    // every desk keeps its chair; a present agent sits in it, an absent one leaves it empty
    Object.keys(SEATS).forEach((id) => {
      const seat = SEATS[id];
      const a = agents.find((x) => x.id === id);
      const sx = seat.fx * W, sy = seat.fy * H;
      if (!a) { drawSeatChair(ctx, seat.chair, sx, sy, W); return; }
      const sheet = SPRITE_MAP[id] || id;
      drawSeated(ctx, sheet, sx, sy, W, seat.chair);
      // status dot above the seat
      const dot = { online: "#3a3a3a", working: "#111111", busy: "#6b6b6b", running: "#111111", off: "#9f9f9a" }[a.status] || "#9f9f9a";
      const headY = sy - W * CHAIR_W_FRAC * 1.95;
      ctx.fillStyle = dot;
      ctx.beginPath(); ctx.arc(sx + W * 0.028, headY, 3.5, 0, Math.PI * 2); ctx.fill();
      // name tag under the chair
      ctx.fillStyle = "rgba(17,17,17,0.72)";
      ctx.beginPath(); ctx.roundRect(sx - 30, sy + 4, 60, 15, 4); ctx.fill();
      ctx.fillStyle = "#ffffff";
      ctx.font = "10px system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(a.name, sx, sy + 15);
    });
  };

  // preload scene layers + atlases, repaint as each arrives
  [loadImage(BG_URL), loadImage(CHAIR_URL)].forEach((e) => { if (!e.ready) e.waiters.push(paint); });
  seated.forEach(({ id }) => {
    const sheet = SPRITE_MAP[id] || id;
    if (!SPRITE_SHEETS.has(sheet)) return;
    const e = loadSprite(sheet);
    if (!e.ready) e.waiters.push(paint);
  });
  paint();
}

function createOfficeStageController(canvas, agents) {
  const dpr = window.devicePixelRatio || 1;
  const W = WAR_W, H = WAR_H;
  canvas.width = W * dpr;
  canvas.height = H * dpr;
  canvas.style.width = "100%";
  const ctx = canvas.getContext("2d");
  loadImage(BG_URL);
  loadImage(CHAIR_URL);

  const roster = agents
    .filter((a) => a && SPRITE_MAP[a.id] && WAR_HOMES[a.id])
    .map((a) => {
      const home = WAR_HOMES[a.id];
      const sheet = SPRITE_MAP[a.id];
      loadSprite(sheet);
      return {
        id: a.id,
        name: a.name || a.id,
        sheet,
        home,
        x: home.x,
        y: home.y,
        tx: home.x,
        ty: home.y,
        mvx: 0,
        mvy: 1,
        walking: false,
        seated: true,
        pauseT: Math.random() * 0.8,
        frameT: 0,
        frameIdx: 0,
        status: a.status || "idle",
      };
    });
  const byId = (id) => roster.find((a) => a.id === id);

  function pickTarget(ag) {
    const busy = ag.status === "working" || ag.status === "running";
    if (busy) {
      ag.tx = ag.home.x;
      ag.ty = ag.home.y;
      ag.pauseT = 1.8 + Math.random() * 1.8;
      return;
    }
    ag.tx = clamp(W * (0.3 + Math.random() * 0.4), 40, W - 40);
    ag.ty = clamp(H * (0.38 + Math.random() * 0.5), 90, H - 24);
    ag.pauseT = 0.8 + Math.random() * 1.8;
  }

  function stepAgent(ag, dt) {
    // 硬规则：工作中的专家目标点永远锁定工位，闲逛目标立即失效
    const busy = ag.status === "working" || ag.status === "running";
    if (busy && (ag.tx !== ag.home.x || ag.ty !== ag.home.y)) {
      ag.tx = ag.home.x;
      ag.ty = ag.home.y;
    }
    const dx = ag.tx - ag.x, dy = ag.ty - ag.y;
    const dist = Math.hypot(dx, dy);
    if (dist < 3) {
      ag.walking = false;
      ag.seated = ag.tx === ag.home.x && ag.ty === ag.home.y;
      ag.pauseT -= dt;
      if (ag.pauseT <= 0) pickTarget(ag);
      return;
    }
    ag.walking = true;
    ag.seated = false;
    const sp = 52 * dt;
    ag.x += (dx / dist) * sp;
    ag.y += (dy / dist) * sp;
    ag.mvx = dx / dist;
    ag.mvy = dy / dist;
    ag.frameT += dt;
    if (ag.frameT > 0.13) {
      ag.frameT = 0;
      ag.frameIdx++;
    }
  }

  const SPRITE_SIZE = W * 0.088;
  function drawAgent(ag) {
    const entry = spriteCache.get(ag.sheet);
    let headTop;
    if (ag.seated) {
      drawSeated(ctx, ag.sheet, ag.x, ag.y, W, ag.home.chair);
      headTop = ag.y - W * CHAIR_W_FRAC * 1.95;
    } else {
      ctx.fillStyle = "rgba(0,0,0,0.26)";
      ctx.beginPath();
      ctx.ellipse(ag.x, ag.y, SPRITE_SIZE * 0.26, SPRITE_SIZE * 0.075, 0, 0, Math.PI * 2);
      ctx.fill();
      const f = facingFrom(ag.mvx, ag.mvy);
      const col = ag.walking ? WALK_COLS[ag.frameIdx % WALK_COLS.length] : IDLE_COLS[0];
      if (entry && entry.ready) drawSpriteCell(ctx, entry, col, f.row, f.flip, ag.x, ag.y, SPRITE_SIZE);
      else {
        ctx.fillStyle = "#d9d9d3";
        ctx.fillRect(ag.x - SPRITE_SIZE / 2, ag.y - SPRITE_SIZE * CELL_FEET, SPRITE_SIZE, SPRITE_SIZE * CELL_FEET);
      }
      headTop = ag.y - SPRITE_SIZE * CELL_FEET;
    }
    const dot = { working: "#111111", running: "#111111", done: "#3a3a3a", idle: "#9f9f9a" }[ag.status] || "#9f9f9a";
    ctx.fillStyle = dot;
    ctx.beginPath();
    ctx.arc(ag.x + 15, headTop + 4, 3.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "rgba(17,17,17,0.72)";
    ctx.beginPath();
    ctx.roundRect(ag.x - 28, ag.y + 5, 56, 14, 4);
    ctx.fill();
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(ag.name, ag.x, ag.y + 15);
  }

  function render() {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.imageSmoothingEnabled = false;
    drawBackground(ctx, W, H);
    roster.forEach((ag) => {
      if (!ag.seated) drawSeatChair(ctx, ag.home.chair, ag.home.x, ag.home.y, W);
    });
    [...roster].sort((a, b) => a.y - b.y).forEach(drawAgent);
  }

  let raf = 0;
  let last = performance.now();
  function tick(ts) {
    const dt = Math.min(0.05, (ts - last) / 1000);
    last = ts;
    roster.forEach((ag) => stepAgent(ag, dt));
    render();
    raf = requestAnimationFrame(tick);
  }
  raf = requestAnimationFrame(tick);

  return {
    setAgentStatus(id, status) {
      const ag = byId(id);
      if (!ag) return;
      ag.status = status === "done" || status === "failed" ? "done" : status || "idle";
      pickTarget(ag);
    },
    stop() {
      cancelAnimationFrame(raf);
    },
  };
}

function demoAgentSummary(agent, report, profile) {
  const contribution = (report.contributions?.[agent] || []).join("；");
  const byAgent = {
    macro: `宏观环境以流动性和政策支持为主线，对本次主题形成中性偏正面的背景约束。${contribution}`,
    research: `${profile.evidence[0] || report.summary} ${contribution}`,
    quant: `已把核心指标转化为可展示的量化证据：${profile.metrics.slice(0, 2).map((m) => `${m.label}${m.display_value}`).join("，")}。`,
    risk: `已识别主要反向证据：${profile.risks.slice(0, 2).join("；")}。`,
    report: `已整合各专家示例证据，保留支持、反对、局限和下一步验证问题。`,
  };
  return byAgent[agent] || contribution || "已完成本次专业研究。";
}

function demoAgentAssumptions(agent) {
  const byAgent = {
    macro: ["政策与利率情景采用中性基准，不假设额外刺激超预期。"],
    research: ["演示样本口径保持可比，财务和行业指标按同一期间阅读。"],
    quant: ["估值和分位测算采用本地演示样本，不代表实时市场价格。"],
    risk: ["压力情景用于展示风险识别流程，不作为真实回撤预测。"],
    report: ["报告只汇总已给出的示例证据，不补造未返回的信息。"],
  };
  return byAgent[agent] || [];
}

function demoAgentLimitations(agent, profile) {
  const shared = "当前为本地示例数据，不代表实际研究结论。";
  const byAgent = {
    macro: [profile.limitations[0], shared],
    research: [profile.limitations[1] || profile.limitations[0], shared],
    quant: [profile.limitations[2] || profile.limitations[0], shared],
    risk: profile.limitations,
    report: [shared, "真实研究需要重新调用模型和数据源生成可验证证据。"],
  };
  return (byAgent[agent] || [shared]).filter(Boolean);
}

function demoAgentRecommendations(agent, profile) {
  const byAgent = {
    macro: [profile.next[0]],
    research: [profile.next[0], profile.next[1]],
    quant: [profile.next[1]],
    risk: [profile.next[2] || profile.next[1]],
    report: profile.next,
  };
  return (byAgent[agent] || profile.next.slice(0, 1)).filter(Boolean);
}

function demoAgentSources(agent, sources) {
  const byAgent = {
    macro: [sources[0]],
    research: [sources[0], sources[1]],
    quant: [sources[2] || sources[0]],
    risk: [sources[2] || sources[0], sources[1]],
    report: sources,
  };
  return (byAgent[agent] || sources.slice(0, 1)).filter(Boolean);
}

// ---------------------------------------------------------------------------
// page: hall (投研大厅 · 界面 01)
// ---------------------------------------------------------------------------
let hallRecIdx = 0;

function pageHall() {
  const wrap = el("div");
  wrap.appendChild(screenTitle("01", "投研大厅", "产品演示使用本地示例数据，适合展示完整研究流程和交互方式。"));

  // ---- hero grid: ask box + LIVE office preview ----
  const grid = el("div", "hall-grid");

  const askPanel = el("div", "panel");
  askPanel.appendChild(el("div", "panel-title", "今天想研究什么？ <span class='title-extra'>演示模式会使用预置案例展示任务拆解和团队协作</span>"));
  const askBox = el("div", "ask-box");
  const ta = el("textarea");
  ta.placeholder = "例如：分析特斯拉（TSLA）的基本面、自动驾驶与机器人业务，并给出估值与风险判断…";
  askBox.appendChild(ta);
  const foot = el("div", "ask-foot");
  const count = el("span", "ask-count", "0 / 500");
  ta.addEventListener("input", () => { count.textContent = `${ta.value.length} / 500`; });
  const startBtn = el("button", "btn btn-primary", "🚀 开始研究");
  startBtn.addEventListener("click", () => {
    toast("正在进入演示澄清流程…");
    navigate("clarify");
  });
  foot.append(count, startBtn);
  askBox.appendChild(foot);
  askPanel.appendChild(askBox);

  // recommended tasks
  const rec = el("div", "rec-row");
  const recLabel = el("span", "rec-label", "演示案例");
  rec.appendChild(recLabel);
  RECOMMENDED_GROUPS[hallRecIdx % RECOMMENDED_GROUPS.length].forEach((t) => {
    const chip = el("button", "chip", esc(t));
    chip.addEventListener("click", () => { ta.value = t.replace(/^\S+\s/, ""); count.textContent = `${ta.value.length} / 500`; ta.focus(); });
    rec.appendChild(chip);
  });
  const shuffle = el("button", "chip", "🔀 换一批");
  shuffle.addEventListener("click", () => { hallRecIdx++; renderPage(); });
  rec.appendChild(shuffle);
  askPanel.appendChild(rec);
  grid.appendChild(askPanel);

  // LIVE office preview
  const officePanel = el("div", "panel");
  officePanel.appendChild(el("div", "panel-title", "投研办公室 <span class='title-extra'>演示专家协作状态</span>"));
  const preview = el("div", "office-preview");
  const canvas = el("canvas");
  preview.appendChild(canvas);
  preview.appendChild(el("div", "live-tag", "<i></i>在线"));
  preview.addEventListener("click", () => navigate("war"));
  officePanel.appendChild(preview);
  const ofeed = el("div", "office-feed");
  ofeed.innerHTML = `<span class="dot"></span><span>${esc(OFFICE_FEED[0])}</span>`;
  officePanel.appendChild(ofeed);
  grid.appendChild(officePanel);
  wrap.appendChild(grid);
  requestAnimationFrame(() => drawOfficeScene(canvas, AGENTS));

  // rotate the office feed line
  let feedIdx = 0;
  const feedTimer = setInterval(() => {
    feedIdx = (feedIdx + 1) % OFFICE_FEED.length;
    const span = ofeed.querySelector("span:last-child");
    if (span) span.textContent = OFFICE_FEED[feedIdx];
  }, 2600);
  registerTeardown(() => clearInterval(feedTimer));

  // ---- online experts ----
  const expertPanel = el("div", "panel");
  expertPanel.style.marginTop = "18px";
  expertPanel.appendChild(el("div", "panel-title", `专家角色 <span class='title-extra'>${AGENTS.filter((a) => a.status !== "off").length} 位角色参与演示流程</span>`));
  const strip = el("div", "expert-strip");
  AGENTS.forEach((a) => {
    const card = el("button", "expert-mini");
    card.appendChild(avatar(a.id, 56, "em-ava"));
    card.appendChild(el("strong", "", esc(a.name)));
    card.appendChild(el("div", "em-role", esc(a.role)));
    card.appendChild(el("span", `badge ${a.status}`, `<span class="dot"></span>${statusText(a.status)}`));
    card.appendChild(el("div", "em-spec", esc(a.specialty)));
    card.addEventListener("click", () => navigate("experts"));
    strip.appendChild(card);
  });
  expertPanel.appendChild(strip);
  wrap.appendChild(expertPanel);

  // ---- overview stats + team radar ----
  const bottom = el("div");
  bottom.style.cssText = "display:grid;grid-template-columns:1.2fr 1fr;gap:18px;margin-top:18px";

  const statPanel = el("div", "panel");
  statPanel.appendChild(el("div", "panel-title", "系统概览"));
  const cards = el("div", "stat-cards");
  const online = AGENTS.filter((a) => a.status !== "off").length;
  const skillTotal = AGENTS.reduce((s, a) => s + (a.skillCount || 0), 0);
  [
    { num: `${HISTORY_TASKS.length}`, label: "演示任务", sub: "预置流程", green: true },
    { num: `${online}/${AGENTS.length}`, label: "专家角色", sub: "演示团队配置" },
    { num: `${skillTotal}`, label: "研究能力", sub: "覆盖主要分析环节" },
    { num: `${REPORTS.length}`, label: "示例报告", sub: "支持追问展示" },
  ].forEach((s) => {
    const c = el("button", "stat-card");
    c.innerHTML = `<div class="sc-num${s.green ? " green" : ""}">${esc(s.num)}</div>
      <div class="sc-label">${esc(s.label)}</div><div class="sc-sub">${esc(s.sub)}</div>`;
    c.addEventListener("click", () => navigate("tasks"));
    cards.appendChild(c);
  });
  statPanel.appendChild(cards);
  bottom.appendChild(statPanel);

  const radarPanel = el("div", "panel");
  radarPanel.appendChild(el("div", "panel-title", "团队能力雷达"));
  const rwrap = el("div");
  rwrap.style.cssText = "display:grid;place-items:center;padding:8px 0";
  const rcanvas = el("canvas");
  rwrap.appendChild(rcanvas);
  radarPanel.appendChild(rwrap);
  bottom.appendChild(radarPanel);
  wrap.appendChild(bottom);
  requestAnimationFrame(() => drawRadar(rcanvas, TEAM_RADAR, 260));

  return wrap;
}

function statusText(s) {
  return { online: "在线", working: "工作中", busy: "忙碌", running: "运行中", off: "离线" }[s] || s;
}

// ---------------------------------------------------------------------------
// page: clarify (界面 02 — Manager 任务澄清)
// ---------------------------------------------------------------------------
const clarifySel = {};
CLARIFY_GROUPS.forEach((g) => { clarifySel[g.key] = new Set(g.def || []); });
const CLARIFY_TASK = { object: "特斯拉（TSLA）", type: "公司深度研究", experts: 5 };

function pageClarify() {
  const layout = el("div", "chat-layout");

  // ---- left: Manager conversation ----
  const left = el("div", "panel chat-col");
  left.appendChild(screenTitle("02", "任务澄清", "演示模式会展示研究经理如何确认关键口径。"));

  const head = el("div", "chat-head");
  head.appendChild(avatar("manager", 46, "pix-ava"));
  const who = el("div", "who");
  who.innerHTML = "<strong>研究经理</strong><small>正在澄清任务需求…</small>";
  head.appendChild(who);
  left.appendChild(head);

  const scroll = el("div", "chat-scroll");
  scroll.appendChild(clarifyMsg("bot", `收到你的研究意向：<b>${esc(CLARIFY_TASK.object)}</b>。在正式开工前，我想先确认几个关键口径，团队会据此安排后续研究。`));

  // clarify option grid, rendered inside a wide Manager bubble
  const gridMsg = el("div", "msg");
  const gAva = el("div", "m-avatar");
  gAva.appendChild(avatar("manager", 38));
  const gBody = el("div", "m-body");
  gBody.style.maxWidth = "none";
  gBody.appendChild(el("div", "m-meta", "<span>研究经理</span><span>关键澄清项</span>"));
  const gridWrap = el("div", "m-bubble");
  gridWrap.style.width = "100%";
  const grid = el("div", "clarify-grid");
  gridWrap.appendChild(grid);
  gBody.appendChild(gridWrap);
  gridMsg.append(gAva, gBody);
  scroll.appendChild(gridMsg);
  renderClarifyGrid(grid);

  scroll.appendChild(clarifyMsg("bot", "确认无误后点击右侧「确认并启动研究」，演示会进入研究作战室并展示协作过程。"));
  left.appendChild(scroll);

  const inputBar = el("div", "chat-inputbar");
  const input = el("input");
  input.type = "text";
  input.placeholder = "补充说明（可选）：例如特别关注的时间段或指标…";
  const send = el("button", "btn btn-primary", "➤");
  const fire = () => {
    const q = input.value.trim();
    if (!q) return;
    input.value = "";
    scroll.appendChild(clarifyMsg("me", q));
    scroll.scrollTop = scroll.scrollHeight;
    setTimeout(() => {
      scroll.appendChild(clarifyMsg("bot", "已记录你的补充说明，会同步到研究口径中。"));
      scroll.scrollTop = scroll.scrollHeight;
    }, 700);
  };
  send.addEventListener("click", fire);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") fire(); });
  inputBar.append(input, send);
  left.appendChild(inputBar);

  // ---- right: live task summary ----
  const right = el("div", "panel chat-col");
  right.id = "clarifySummary";
  layout.append(left, right);
  renderClarifySummary(right);
  return layout;
}

function clarifyMsg(role, html) {
  const me = role === "me";
  const node = el("div", `msg${me ? " me" : ""}`);
  const ava = el("div", "m-avatar");
  ava.appendChild(avatar(me ? "user" : "manager", 38));
  const body = el("div", "m-body");
  body.appendChild(el("div", "m-meta", `<span>${me ? "你" : "研究经理"}</span><span>${nowClock()}</span>`));
  body.appendChild(el("div", "m-bubble", html));
  node.append(ava, body);
  return node;
}

function renderClarifyGrid(grid) {
  grid.innerHTML = "";
  CLARIFY_GROUPS.forEach((g) => {
    const card = el("div", "opt-card");
    card.appendChild(el("h5", "", `${esc(g.title)} <small>${g.multi ? "可多选" : "单选"}</small>`));
    const list = el("div", "opt-list");
    g.items.forEach((label, i) => {
      const sel = clarifySel[g.key].has(i);
      const item = el("button", `opt-item${sel ? " sel" : ""}`);
      item.innerHTML = `<span>${esc(label)}</span>${sel ? '<span class="tick">✓</span>' : ""}`;
      item.addEventListener("click", () => {
        toggleClarify(g, i);
        renderClarifyGrid(grid);
        renderClarifySummary($("#clarifySummary"));
      });
      list.appendChild(item);
    });
    card.appendChild(list);
    grid.appendChild(card);
  });
}

function toggleClarify(g, i) {
  const set = clarifySel[g.key];
  if (!g.multi) { set.clear(); set.add(i); return; }
  const allIdx = g.allItem ? g.items.indexOf(g.allItem) : -1;
  if (i === allIdx) { set.clear(); set.add(i); return; }
  if (set.has(i)) set.delete(i); else set.add(i);
  if (allIdx >= 0) set.delete(allIdx);
  if (set.size === 0 && allIdx >= 0) set.add(allIdx);
}

function clarifyValue(key) {
  const g = CLARIFY_GROUPS.find((x) => x.key === key);
  return [...clarifySel[key]].sort((a, b) => a - b).map((i) => g.items[i]).join("、") || "—";
}

function renderClarifySummary(panel) {
  if (!panel) return;
  panel.innerHTML = "";
  panel.appendChild(el("div", "panel-title", "任务摘要"));

  const kv = el("div", "summary-kv");
  [
    ["研究对象", CLARIFY_TASK.object],
    ["任务类型", CLARIFY_TASK.type],
    ["投资周期", clarifyValue("period")],
    ["风险偏好", clarifyValue("risk")],
    ["研究重点", clarifyValue("focus")],
  ].forEach(([k, v]) => {
    kv.appendChild(el("div", "", `<div class="k">${esc(k)}</div><div>${esc(v)}</div>`));
  });
  panel.appendChild(kv);

  panel.appendChild(el("div", "follow-sec-title", "分析范围"));
  const check = el("div", "check-list");
  ANALYSIS_SCOPE.forEach((s) => {
    check.appendChild(el("div", "ck on", `<i>✓</i><span>${esc(s)}</span>`));
  });
  panel.appendChild(check);

  panel.appendChild(el("div", "follow-sec-title", "预计投入"));
  const yc = el("div", "yield-cards");
  yc.innerHTML = `
    <div class="yc"><strong>~4<small>min</small></strong><span>预计耗时</span></div>
    <div class="yc"><strong>${CLARIFY_TASK.experts}</strong><span>参与专家</span></div>
    <div class="yc"><strong>5</strong><span>分析方法</span></div>`;
  panel.appendChild(yc);

  const go = el("button", "btn btn-primary", "🚀 确认并启动研究");
  go.style.cssText = "width:100%;margin-top:16px";
  go.addEventListener("click", () => {
    toast("任务已启动，进入研究作战室");
    navigate("war");
  });
  panel.appendChild(go);

  const edit = el("button", "btn-ghost", "‹ 返回大厅重新描述");
  edit.style.cssText = "width:100%;margin-top:8px";
  edit.addEventListener("click", () => navigate("hall"));
  panel.appendChild(edit);
}

// ---------------------------------------------------------------------------
// page: war room (界面 03) — autonomous sprite office + script-driven execution
// ---------------------------------------------------------------------------
const WAR_W = 760, WAR_H = Math.round(WAR_W / BG_RATIO);
// Each agent's "home" is its desk seat, derived from the shared SEATS fractions.
const WAR_HOMES = Object.fromEntries(
  Object.entries(SEATS).map(([id, s]) => [id, { x: s.fx * WAR_W, y: s.fy * WAR_H, chair: s.chair }]),
);
const DAG_LAYERS = [
  ["manager"],
  ["macro", "research", "quant"],
  ["risk"],
  ["report"],
];
const DAG_EDGES = [
  ["manager", "macro"], ["manager", "research"], ["manager", "quant"],
  ["macro", "risk"], ["research", "risk"], ["quant", "risk"], ["risk", "report"],
];
const DAG_NODE_IDS = DAG_LAYERS.flat();
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

function pageWarRoom() {
  const wrap = el("div", "war-room-page");

  // ---- head ----
  const head = el("div", "war-head");
  head.appendChild(el("h1", "", "研究作战室"));
  head.appendChild(el("span", "sub", "产品演示 · 预置场景 · 不调用外部模型或数据源"));
  const task = el("div", "war-task");
  task.appendChild(el("span", "wt-name", esc(DEMO_TASK.title)));
  const badge = el("span", "badge running", '<span class="dot"></span>执行中');
  task.appendChild(badge);
  head.appendChild(task);
  wrap.appendChild(head);

  const grid = el("div", "war-grid");

  // ================= LEFT: task-graph DAG =================
  const leftCol = el("div", "panel war-left-col");
  leftCol.appendChild(el("div", "panel-title", "任务执行流"));
  const dag = el("div", "dag-wrap dag-stack");
  const edgeEls = {};
  const dagNodes = {};
  DAG_LAYERS.forEach((ids, layerIndex) => {
    if (layerIndex > 0) dag.appendChild(el("div", "dag-layer-join", "↓"));
    const layer = el("div", `dag-layer${ids.length === 1 ? " single" : " multi"}`);
    layer.style.setProperty("--dag-cols", String(ids.length));
    ids.forEach((id) => {
      const a = agentById(id);
      const node = el("button", "dag-node st-idle");
      node.appendChild(avatar(id, 34, "dn-ava"));
      node.appendChild(el("strong", "", esc(a.name)));
      node.appendChild(el("small", "", esc(a.role)));
      const deps = DAG_EDGES.filter(([, to]) => to === id).map(([from]) => agentById(from)?.name || from);
      if (deps.length) node.appendChild(el("span", "dag-deps", `依赖 ${esc(deps.join(" / "))}`));
      node.appendChild(el("span", "badge off dn-badge", '<span class="dot"></span>待命'));
      node.addEventListener("click", () => navigate("experts"));
      dagNodes[id] = node;
      layer.appendChild(node);
    });
    dag.appendChild(layer);
  });
  leftCol.appendChild(dag);
  grid.appendChild(leftCol);

  // ================= CENTER: live stage + progress + timeline =================
  const centerCol = el("div", "war-center-col");
  const stagePanel = el("div", "panel");
  stagePanel.appendChild(el("div", "panel-title", "作战室演示画面 <span class='title-extra'>展示专家协作和任务流转</span>"));
  const stage = el("div", "office-stage");
  const canvas = el("canvas");
  stage.appendChild(canvas);
  const bubbleLayer = el("div", "bubble-layer");
  stage.appendChild(bubbleLayer);
  stagePanel.appendChild(stage);

  // overall + per-agent progress
  const prog = el("div", "progress-row");
  const pmain = el("div");
  pmain.innerHTML = '<div style="font-size:12px;color:var(--text-2);margin-bottom:6px">整体进度 <b class="p-pct" style="color:var(--cyan)">0%</b></div><div class="pbar"><i style="width:0%"></i></div>';
  prog.appendChild(pmain);
  const pstats = {
    done: el("div", "pstat", '<strong>0</strong><span>已完成</span>'),
    working: el("div", "pstat", '<strong>0</strong><span>进行中</span>'),
    logs: el("div", "pstat", '<strong>0</strong><span>日志</span>'),
    elapsed: el("div", "pstat", '<strong>0s</strong><span>用时</span>'),
  };
  prog.append(pstats.done, pstats.working, pstats.logs, pstats.elapsed);
  stagePanel.appendChild(prog);
  centerCol.appendChild(stagePanel);

  // companion interpretation feed（挂到右栏，与日志同列，保持中栏单屏）
  const companionPanel = el("div", "panel companion-panel");
  companionPanel.style.marginTop = "0";
  companionPanel.appendChild(el("div", "panel-title", "🔍 专家解读"));
  const companionFeed = el("div", "companion-feed");
  companionPanel.appendChild(companionFeed);

  // demo coach classroom: replays labeled sample narrations on a timer
  const classroom = createClassroomPanel({
    demo: true,
    agentName: (id) => agentById(id)?.name || id,
  });
  (DEMO_COACH.narrations || []).forEach((n, i) => {
    setTimeout(() => {
      if (!classroom.root.isConnected) return;
      classroom.push(n);
      if (i === DEMO_COACH.narrations.length - 1) classroom.finish();
    }, 1500 + i * 2600);
  });

  // timeline
  const tlPanel = el("div", "panel");
  tlPanel.style.marginTop = "14px";
  tlPanel.appendChild(el("div", "panel-title", "演示时间轴"));
  const tl = el("div", "timeline");
  const tlEvents = WAR_SCRIPT.filter((e) => e.type === "timeline");
  const tlTrack = el("div", "tl-track");
  const tlFill = el("div", "tl-fill");
  tlFill.style.width = "0%";
  tlTrack.appendChild(tlFill);
  const tlNodeEls = [];
  tlEvents.forEach((e) => {
    const dot = el("button", "tl-node");
    dot.style.left = `${(e.t / 60) * 100}%`;
    tlTrack.appendChild(dot);
    tlNodeEls.push(dot);
  });
  tl.appendChild(tlTrack);
  const tlLabels = el("div", "tl-labels");
  tlEvents.forEach((e) => {
    tlLabels.appendChild(el("span", "tl-label", `${esc(e.label)}<span class="t">${esc(e.clock)}</span>`));
  });
  tl.appendChild(tlLabels);
  const controls = el("div", "tl-controls");
  const playBtn = el("button", "btn", "⏸ 暂停");
  const speedSel = el("select");
  [["1", "1x"], ["2", "2x"], ["4", "4x"]].forEach(([v, t]) => {
    const o = el("option", "", t); o.value = v; speedSel.appendChild(o);
  });
  const replayBtn = el("button", "btn", "↻ 重播");
  controls.append(el("span", "", '<span style="color:var(--text-2);font-size:12px">播放速度</span>'), speedSel, playBtn, replayBtn);
  tl.appendChild(controls);
  tlPanel.appendChild(tl);
  centerCol.appendChild(tlPanel);
  grid.appendChild(centerCol);

  // ================= RIGHT: interpretation + classroom + logs =================
  // （任务摘要与专业分析方法挪到左栏 DAG 下方，右栏集中放动态信息流）
  const rightCol = el("div", "war-right-col");
  const sumPanel = el("div", "panel");
  sumPanel.style.marginTop = "14px";
  sumPanel.appendChild(el("div", "panel-title", "任务摘要"));
  const kv = el("div", "kv-list");
  [
    ["演示场景", DEMO_TASK.short],
    ["任务类型", DEMO_TASK.type],
    ["数据口径", "本地示例数据"],
    ["流程状态", "脚本化演示"],
  ].forEach(([k, v]) => {
    kv.appendChild(el("div", "kv", `<span class="k">${esc(k)}</span><span>${esc(v)}</span>`));
  });
  sumPanel.appendChild(kv);
  leftCol.appendChild(sumPanel);

  const skillPanel = el("div", "panel");
  skillPanel.style.marginTop = "14px";
  skillPanel.appendChild(el("div", "panel-title", "专业分析方法"));
  const skillCounts = {};
  const skillRows = {};
  Object.keys(SKILL_FINAL_COUNTS).forEach((name) => {
    skillCounts[name] = 0;
    const row = el("div", "skill-row");
    row.innerHTML = `<span>🧩</span><span>${esc(name)}</span><span class="sk-count">0</span>`;
    skillRows[name] = row;
    skillPanel.appendChild(row);
  });
  leftCol.appendChild(skillPanel);

  rightCol.appendChild(companionPanel);
  rightCol.appendChild(classroom.root);

  const logPanel = el("div", "panel");
  logPanel.style.marginTop = "14px";
  logPanel.appendChild(el("div", "panel-title", "实时日志"));
  const logEl = el("div", "log-list");
  logPanel.appendChild(logEl);
  rightCol.appendChild(logPanel);
  grid.appendChild(rightCol);

  wrap.appendChild(grid);

  // ---------------- engine state ----------------
  const agents = Object.keys(WAR_HOMES).map((id) => {
    const home = WAR_HOMES[id];
    const a = agentById(id);
    loadSprite(SPRITE_MAP[id] || id);
    return {
      id, name: a ? a.name : id, sheet: SPRITE_MAP[id] || id,
      x: home.x, y: home.y, tx: home.x, ty: home.y, home,
      mvx: 0, mvy: 1, walking: false, seated: true, pauseT: Math.random() * 1.5,
      frameT: 0, frameIdx: 0, status: "idle", say: null, bubbleEl: null,
    };
  });
  const agentById2 = (id) => agents.find((a) => a.id === id);

  const state = { clock: 0, speed: 1, playing: true, ptr: 0, logs: 0, lastPct: -1 };

  // Working experts return to their desk seats; everyone else keeps strolling.
  function pickWander(ag) {
    const busy = ag.status === "working" || ag.status === "running";
    if (busy) {
      ag.tx = ag.home.x;
      ag.ty = ag.home.y;
      ag.pauseT = 2.5 + Math.random() * 3;
    } else {
      // stroll target: central walkable floor area away from the desks
      ag.tx = clamp(WAR_W * (0.3 + Math.random() * 0.4), 40, WAR_W - 40);
      ag.ty = clamp(WAR_H * (0.38 + Math.random() * 0.5), 90, WAR_H - 24);
      ag.pauseT = 0.8 + Math.random() * 1.8;
    }
  }
  function gather(ids) {
    // 只有非工作状态的专家才会离开工位去圆桌；工作中的专家留在工位发言
    const cx = TABLE_CENTER.fx * WAR_W, cy = TABLE_CENTER.fy * WAR_H, n = ids.length;
    ids.forEach((id, i) => {
      const ag = agentById2(id);
      if (!ag) return;
      if (ag.status === "working" || ag.status === "running") return;
      const ang = -Math.PI / 2 + (i * 2 * Math.PI) / Math.max(n, 1);
      ag.tx = clamp(cx + Math.cos(ang) * WAR_W * 0.11, 40, WAR_W - 40);
      ag.ty = clamp(cy + Math.sin(ang) * WAR_H * 0.13, 90, WAR_H - 24);
      ag.pauseT = 3;
    });
  }

  function appendLog(who, text, color, clockStr) {
    const line = el("div", "log-line");
    line.innerHTML = `<span class="lt">${esc(clockStr)}</span><span class="la" style="color:${color || "var(--text-2)"}">${esc(who)}</span><span>${esc(text)}</span>`;
    logEl.appendChild(line);
    while (logEl.children.length > 40) logEl.removeChild(logEl.firstChild);
    logEl.scrollTop = logEl.scrollHeight;
    state.logs++;
  }

  const DAG_LABEL = { idle: "待命", working: "工作中", running: "运行中", done: "完成" };
  function setDag(id, status) {
    const node = dagNodes[id];
    if (!node) return;
    node.className = `dag-node st-${status}`;
    const b = node.querySelector(".dn-badge");
    if (b) {
      const cls = status === "done" ? "done" : status === "idle" ? "off" : status;
      b.className = `badge ${cls} dn-badge`;
      b.innerHTML = `<span class="dot"></span>${DAG_LABEL[status] || status}`;
    }
    Object.entries(edgeEls).forEach(([key, ln]) => {
      if (key.startsWith(`${id}-`) && (status === "working" || status === "running" || status === "done")) {
        ln.setAttribute("stroke", "#111111");
        ln.setAttribute("stroke-width", "0.8");
      }
    });
  }

  function say(id, text, dur) {
    const ag = agentById2(id);
    if (!ag) return;
    ag.say = { text, until: state.clock + (dur || 3) };
  }

  function clockStr() {
    // map 0..60s script to the demo 10:15 → 10:28 window for log timestamps
    const base = 10 * 60 + 15;
    const mins = base + Math.round((state.clock / 60) * 13);
    return `${String(Math.floor(mins / 60)).padStart(2, "0")}:${String(mins % 60).padStart(2, "0")}`;
  }

  function dispatch(ev) {
    const cs = ev.clock || clockStr();
    switch (ev.type) {
      case "log": appendLog(ev.agent, ev.text, ev.color, cs); break;
      case "work": setDag(ev.agent, "working"); { const a = agentById2(ev.agent); if (a) { a.status = "working"; pickWander(a); } } break;
      case "dag": setDag(ev.agent, ev.status); break;
      case "say": say(ev.agent, ev.text, ev.dur); break;
      case "done": setDag(ev.agent, "done"); { const a = agentById2(ev.agent); if (a) a.status = "done"; }
        if (DEMO_COMPANION[ev.agent]) renderCompanionCard(companionFeed, DEMO_COMPANION[ev.agent]);
        break;
      case "skill":
        skillCounts[ev.name] = ev.n;
        if (skillRows[ev.name]) {
          skillRows[ev.name].querySelector(".sk-count").textContent = ev.n;
          skillRows[ev.name].classList.add("hl");
          setTimeout(() => skillRows[ev.name] && skillRows[ev.name].classList.remove("hl"), 900);
        }
        break;
      case "visit":
        gather([ev.from, ev.to]);
        (ev.lines || []).forEach((l, i) => say(l.agent, l.text, 3 + i));
        break;
      case "roundtable":
        gather(ev.agents || []);
        (ev.lines || []).forEach((l, i) => say(l.agent, l.text, 3 + i));
        break;
      case "timeline": break; // handled by clock-driven node states
      case "finish":
        agents.forEach((a) => { a.status = "done"; setDag(a.id, "done"); });
        badge.className = "badge done";
        badge.innerHTML = '<span class="dot"></span>已完成';
        appendLog("系统", "AlphaBit Coach 任务处理完成", "#6e6e6e", cs);
        setTimeout(() => navigate("reports", REPORTS[0].id), 0);
        break;
    }
  }

  function stepAgent(ag, dt) {
    // 硬规则：工作中的专家目标点永远锁定工位（gather/闲逛目标立即失效），
    // 讨论台词仍以气泡形式显示在工位上方
    const busy = ag.status === "working" || ag.status === "running";
    if (busy && (ag.tx !== ag.home.x || ag.ty !== ag.home.y)) {
      ag.tx = ag.home.x;
      ag.ty = ag.home.y;
    }
    const dx = ag.tx - ag.x, dy = ag.ty - ag.y;
    const dist = Math.hypot(dx, dy);
    if (dist < 3) {
      ag.walking = false;
      ag.seated = ag.tx === ag.home.x && ag.ty === ag.home.y;
      ag.pauseT -= dt;
      if (ag.pauseT <= 0) pickWander(ag);
    } else {
      ag.walking = true;
      ag.seated = false;
      const sp = 52 * dt;
      ag.x += (dx / dist) * sp;
      ag.y += (dy / dist) * sp;
      ag.mvx = dx / dist; ag.mvy = dy / dist;
      ag.frameT += dt;
      if (ag.frameT > 0.13) { ag.frameT = 0; ag.frameIdx++; }
    }
  }

  const dpr = window.devicePixelRatio || 1;
  canvas.width = WAR_W * dpr;
  canvas.height = WAR_H * dpr;
  const ctx = canvas.getContext("2d");
  loadImage(BG_URL);
  loadImage(CHAIR_URL);

  function drawRoom() {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.imageSmoothingEnabled = false;
    drawBackground(ctx, WAR_W, WAR_H);
  }

  const SPRITE_SIZE = WAR_W * 0.088; // walking sprite cell size (~66 at 760px wide)
  function drawAgent(ag) {
    const entry = spriteCache.get(ag.sheet);
    let headTop;
    if (ag.seated) {
      drawSeated(ctx, ag.sheet, ag.x, ag.y, WAR_W, ag.home.chair);
      headTop = ag.y - WAR_W * CHAIR_W_FRAC * 1.95;
    } else {
      // ground shadow under the feet
      ctx.fillStyle = "rgba(0,0,0,0.26)";
      ctx.beginPath(); ctx.ellipse(ag.x, ag.y, SPRITE_SIZE * 0.26, SPRITE_SIZE * 0.075, 0, 0, Math.PI * 2); ctx.fill();
      const f = facingFrom(ag.mvx, ag.mvy);
      const col = ag.walking ? WALK_COLS[ag.frameIdx % WALK_COLS.length] : IDLE_COLS[0];
      if (entry && entry.ready) drawSpriteCell(ctx, entry, col, f.row, f.flip, ag.x, ag.y, SPRITE_SIZE);
      else { ctx.fillStyle = "#d9d9d3"; ctx.fillRect(ag.x - SPRITE_SIZE / 2, ag.y - SPRITE_SIZE * CELL_FEET, SPRITE_SIZE, SPRITE_SIZE * CELL_FEET); }
      headTop = ag.y - SPRITE_SIZE * CELL_FEET;
    }
    // status dot near the head
    const dot = { working: "#111111", running: "#111111", done: "#3a3a3a", idle: "#9f9f9a" }[ag.status] || "#9f9f9a";
    ctx.fillStyle = dot;
    ctx.beginPath(); ctx.arc(ag.x + 15, headTop + 4, 3.5, 0, Math.PI * 2); ctx.fill();
    // name tag
    ctx.fillStyle = "rgba(17,17,17,0.72)";
    ctx.beginPath(); ctx.roundRect(ag.x - 28, ag.y + 5, 56, 14, 4); ctx.fill();
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(ag.name, ag.x, ag.y + 15);
  }

  function render() {
    drawRoom();
    // persistent chairs: any seat whose owner has stepped away still shows its chair
    agents.forEach((ag) => {
      if (!ag.seated) drawSeatChair(ctx, ag.home.chair, ag.home.x, ag.home.y, WAR_W);
    });
    [...agents].sort((a, b) => a.y - b.y).forEach(drawAgent);
  }

  function updateBubbles() {
    agents.forEach((ag) => {
      const active = ag.say && state.clock < ag.say.until;
      if (active) {
        if (!ag.bubbleEl) {
          ag.bubbleEl = el("div", "say-bubble");
          bubbleLayer.appendChild(ag.bubbleEl);
        }
        ag.bubbleEl.innerHTML = `<span class="sb-name">${esc(ag.name)}</span>${esc(ag.say.text)}`;
        ag.bubbleEl.style.left = `${(ag.x / WAR_W) * 100}%`;
        ag.bubbleEl.style.top = `${((ag.y - 62) / WAR_H) * 100}%`;
      } else if (ag.bubbleEl) {
        ag.bubbleEl.remove();
        ag.bubbleEl = null;
      }
    });
  }

  function updateHud() {
    const pct = Math.min(100, Math.round((state.clock / 60) * 100));
    if (pct !== state.lastPct) {
      state.lastPct = pct;
      pmain.querySelector(".p-pct").textContent = `${pct}%`;
      pmain.querySelector(".pbar i").style.width = `${pct}%`;
      pstats.done.querySelector("strong").textContent = agents.filter((a) => a.status === "done").length;
      pstats.working.querySelector("strong").textContent = agents.filter((a) => a.status === "working" || a.status === "running").length;
      pstats.logs.querySelector("strong").textContent = state.logs;
      pstats.elapsed.querySelector("strong").textContent = `${Math.round(state.clock)}s`;
    }
    tlFill.style.width = `${(state.clock / 60) * 100}%`;
    tlEvents.forEach((e, i) => {
      const node = tlNodeEls[i];
      const done = state.clock >= e.t;
      node.className = `tl-node${done ? " done" : ""}${!done && state.clock >= e.t - 2 ? " now" : ""}`;
    });
  }

  function resetRun() {
    state.clock = 0; state.ptr = 0; state.logs = 0; state.lastPct = -1;
    logEl.innerHTML = "";
    Object.keys(skillCounts).forEach((n) => { skillCounts[n] = 0; skillRows[n].querySelector(".sk-count").textContent = "0"; });
    agents.forEach((a) => { a.status = "idle"; a.say = null; if (a.bubbleEl) { a.bubbleEl.remove(); a.bubbleEl = null; } });
    DAG_NODE_IDS.forEach((id) => setDag(id, "idle"));
    DAG_EDGES.forEach(([a, b]) => {
      const ln = edgeEls[`${a}-${b}`];
      if (!ln) return;
      ln.setAttribute("stroke", "#d9d9d3");
      ln.setAttribute("stroke-width", "0.5");
    });
    badge.className = "badge running";
    badge.innerHTML = '<span class="dot"></span>执行中';
    state.playing = true;
    playBtn.textContent = "⏸ 暂停";
  }

  playBtn.addEventListener("click", () => {
    state.playing = !state.playing;
    playBtn.textContent = state.playing ? "⏸ 暂停" : "▶ 继续";
  });
  speedSel.addEventListener("change", () => { state.speed = Number(speedSel.value) || 1; });
  replayBtn.addEventListener("click", resetRun);

  // ---------------- rAF loop ----------------
  let raf = 0;
  let last = performance.now();
  function tick(ts) {
    const dtReal = Math.min(0.05, (ts - last) / 1000);
    last = ts;
    const dt = dtReal * state.speed;
    if (state.playing && state.clock < 60) {
      state.clock += dt;
      while (state.ptr < WAR_SCRIPT.length && WAR_SCRIPT[state.ptr].t <= state.clock) {
        dispatch(WAR_SCRIPT[state.ptr++]);
      }
      if (state.clock >= 60) { state.clock = 60; state.playing = false; playBtn.textContent = "▶ 继续"; }
      updateHud();
    }
    // agents always wander (autonomous movement), a touch slower when paused
    agents.forEach((a) => stepAgent(a, (state.playing ? dt : dtReal) * (state.playing ? 1 : 0.5)));
    render();
    updateBubbles();
    raf = requestAnimationFrame(tick);
  }
  raf = requestAnimationFrame(tick);
  registerTeardown(() => {
    cancelAnimationFrame(raf);
    agents.forEach((a) => { if (a.bubbleEl) a.bubbleEl.remove(); });
  });

  return wrap;
}

// ---------------------------------------------------------------------------
// page: experts (master-detail, 界面 04)
// ---------------------------------------------------------------------------
let expertSel = "manager";
let expertTab = "cap";
let expertQuery = "";
let expertFilter = "all";

function pageExperts() {
  const layout = el("div", "experts-layout");
  const left = el("div", "panel");
  left.appendChild(screenTitle("04", "专家中心", "AlphaBit Coach 专家团队由领域顶尖 AI Agent 组成，覆盖宏观、行业、量化、风险、研究与报告全链路。"));

  // toolbar
  const toolbar = el("div", "experts-toolbar");
  const search = el("input");
  search.type = "text";
  search.placeholder = "🔍 搜索专家或技能…";
  search.value = expertQuery;
  search.addEventListener("input", () => { expertQuery = search.value; renderExpertGrid(grid); });
  const filter = el("select");
  [["all", "全部状态"], ["online", "在线"], ["working", "工作中"], ["busy", "忙碌"]].forEach(([v, t]) => {
    const o = el("option", "", esc(t)); o.value = v; if (v === expertFilter) o.selected = true; filter.appendChild(o);
  });
  filter.addEventListener("change", () => { expertFilter = filter.value; renderExpertGrid(grid); });
  toolbar.append(search, filter);
  left.appendChild(toolbar);

  const grid = el("div", "experts-grid");
  left.appendChild(grid);
  renderExpertGrid(grid);

  // footer counts
  const foot = el("div", "experts-foot");
  const by = (s) => AGENTS.filter((a) => a.status === s).length;
  foot.innerHTML = `<span>共 ${AGENTS.length} 位专家</span>
    <span><span class="dot ok"></span>在线 ${by("online")}</span>
    <span><span class="dot" style="background:#111111"></span>工作中 ${by("working")}</span>
    <span><span class="dot warn"></span>忙碌 ${by("busy")}</span>
    <span><span class="dot"></span>离线 ${by("off")}</span>`;
  left.appendChild(foot);

  layout.appendChild(left);
  const detail = el("div", "panel");
  detail.id = "expertDetail";
  layout.appendChild(detail);
  renderExpertDetail(detail);
  return layout;
}

function renderExpertGrid(grid) {
  grid.innerHTML = "";
  const q = expertQuery.trim();
  AGENTS.filter((a) => {
    if (expertFilter !== "all" && a.status !== expertFilter) return false;
    if (!q) return true;
    const hay = `${a.name} ${a.role} ${a.specialty} ${(a.skills || []).map((s) => s.name).join(" ")}`;
    return hay.includes(q);
  }).forEach((a) => {
    const enabled = store.state.agentEnabled[a.id] !== false;
    const card = el("button", `expert-card${a.id === expertSel ? " sel" : ""}${enabled ? "" : " off"}`);
    card.appendChild(avatar(a.id, 64, "ec-ava"));
    card.appendChild(el("strong", "", esc(a.name)));
    card.appendChild(el("div", "", `<span style="color:var(--text-2);font-size:11.5px">${esc(a.role)}</span> <span class="badge ${a.status}"><span class="dot"></span>${statusText(a.status)}</span>`));
    card.appendChild(el("div", "ec-spec", esc(a.specialty)));
    card.appendChild(el("div", "ec-desc", `分析方法 <b style="color:var(--cyan)">${a.skillCount}</b> 项`));
    card.appendChild(el("div", "ec-desc", esc(a.desc)));
    card.addEventListener("click", () => {
      expertSel = a.id; expertTab = "cap";
      renderExpertGrid(grid);
      renderExpertDetail($("#expertDetail"));
    });
    grid.appendChild(card);
  });
}

function renderExpertDetail(panel) {
  if (!panel) return;
  const a = agentById(expertSel) || AGENTS[0];
  panel.innerHTML = "";

  const head = el("div", "detail-head");
  head.appendChild(avatar(a.id, 74, "pix-ava dh-ava"));
  const hinfo = el("div");
  hinfo.style.flex = "1";
  hinfo.innerHTML = `<div style="font-size:20px;font-weight:700">${esc(a.name)}</div>
    <div style="color:var(--text-2);font-size:12.5px">${esc(a.role)} <span class="badge ${a.status}"><span class="dot"></span>${statusText(a.status)}</span></div>`;
  head.appendChild(hinfo);
  panel.appendChild(head);

  panel.appendChild(el("p", "", `<span style="color:var(--text-2);line-height:1.7">${esc(a.desc)}</span>`));

  const stars = "★★★★★".slice(0, Math.round(a.rating)) + "☆☆☆☆☆".slice(0, 5 - Math.round(a.rating));
  const stats = el("div", "detail-stats");
  stats.innerHTML = `
    <div class="ds"><strong>${esc(a.joined)}</strong><span>加入时间</span></div>
    <div class="ds"><strong>${esc(a.years)}</strong><span>经验年限</span></div>
    <div class="ds"><strong>${esc(a.completion)}</strong><span>任务完成率</span></div>
    <div class="ds"><strong style="color:var(--yellow)">${a.rating}</strong><span>${stars}</span></div>`;
  panel.appendChild(stats);

  const tabs = el("div", "tabs");
  [["cap", "能力概览"], ["tasks", "近期任务"], ["contrib", "贡献表现"], ["skills", "分析方法"], ["config", "配置管理"]].forEach(([k, t]) => {
    const tab = el("button", `tab${expertTab === k ? " active" : ""}`, esc(t));
    tab.addEventListener("click", () => { expertTab = k; renderExpertDetail(panel); });
    tabs.appendChild(tab);
  });
  panel.appendChild(tabs);

  const body = el("div");
  panel.appendChild(body);

  if (expertTab === "cap") {
    body.appendChild(el("div", "follow-sec-title", "核心能力"));
    const bars = el("div", "cap-bars");
    (a.capabilities || []).forEach((c) => {
      bars.appendChild(el("div", "cap-bar", `<span>${esc(c.label)}</span>
        <span class="cb-track"><i style="width:${c.pct}%"></i></span>
        <span style="text-align:right;color:var(--green)">${c.pct}%</span>`));
    });
    body.appendChild(bars);
    body.appendChild(el("div", "follow-sec-title", "能力雷达"));
    const rwrap = el("div");
    rwrap.style.cssText = "display:grid;place-items:center;padding:6px 0";
    const canvas = el("canvas");
    rwrap.appendChild(canvas);
    body.appendChild(rwrap);
    requestAnimationFrame(() => drawRadar(canvas, a.radar, 240));
  } else if (expertTab === "tasks") {
    (a.recentTasks || []).forEach((t) => {
      const row = el("div", "task-row");
      row.innerHTML = `<span style="flex:1">${esc(t.title)}</span>
        <span class="tr-tag">${esc(t.tag)}</span>
        <span class="badge ${t.status === "running" ? "running" : "done"}"><span class="dot"></span>${t.status === "running" ? "进行中" : "完成"}</span>
        <span class="tr-time">${esc(t.time)}</span>`;
      body.appendChild(row);
    });
  } else if (expertTab === "contrib") {
    const grid = el("div", "detail-stats");
    grid.style.gridTemplateColumns = "repeat(3,1fr)";
    grid.innerHTML = `
      <div class="ds"><strong>${a.recentTasks ? a.recentTasks.length + 24 : 28}</strong><span>近30天任务</span></div>
      <div class="ds"><strong style="color:var(--green)">96%</strong><span>完成率</span></div>
      <div class="ds"><strong>${a.skillCount}</strong><span>影响策略</span></div>`;
    body.appendChild(grid);
    body.appendChild(el("div", "follow-sec-title", "贡献趋势（近 5 周）"));
    const canvas = el("canvas");
    const box = el("div", "chart-box");
    box.appendChild(canvas);
    body.appendChild(box);
    const trend = { title: "", labels: ["W1", "W2", "W3", "W4", "W5"], series: [{ name: "贡献值", color: "#111111", data: [62, 70, 66, 82, 90] }] };
    requestAnimationFrame(() => drawLineChart(canvas, trend));
  } else if (expertTab === "skills") {
    body.appendChild(el("div", "follow-sec-title", `专业分析方法 · ${a.skillCount} 项`));
    (a.skills || []).forEach((s) => {
      const row = el("div", "skill-row");
      row.innerHTML = `<span>🧩</span><span>${esc(s.name)}</span><span class="sk-count" style="color:var(--text-3)">${esc(s.type)}</span>`;
      body.appendChild(row);
    });
  } else if (expertTab === "config") {
    const enabled = store.state.agentEnabled[a.id] !== false;
    const enable = el("div", "op-enable");
    enable.innerHTML = `<div><strong>启用该专家</strong><div class="op-note">停用后，研究经理将不会把该专家纳入后续任务。</div></div>`;
    const sw = el("button", `switch${enabled ? " on" : ""}`);
    if (a.id === "manager") { sw.classList.add("disabled"); }
    sw.addEventListener("click", () => {
      if (a.id === "manager") { toast("研究经理负责统筹任务，不能停用"); return; }
      store.setAgentEnabled(a.id, !(store.state.agentEnabled[a.id] !== false));
      renderExpertDetail(panel);
      renderExpertGrid($(".experts-grid"));
    });
    enable.appendChild(sw);
    body.appendChild(enable);
  }
}

// ---------------------------------------------------------------------------
// page: tasks (report + demo history list)
// ---------------------------------------------------------------------------
function pageTasks() {
  const wrap = el("div", "panel");
  wrap.appendChild(el("div", "panel-title", "历史记录 <span class='title-extra'>历史报告</span>"));
  const list = el("div", "task-list");
  REPORTS.forEach((r) => {
    const item = el("button", "task-item");
    item.appendChild(el("span", "ri-ico", "📄"));
    item.appendChild(el("div", "", `<div class="ti-title">${esc(r.title)}</div><div class="ti-sub">${esc(r.kind)} · ${esc(r.doneAt)}</div>`));
    item.appendChild(el("span", "ti-go", "›"));
    item.addEventListener("click", () => navigate("reports", r.id));
    list.appendChild(item);
  });
  wrap.appendChild(list);
  return wrap;
}

// ---------------------------------------------------------------------------
// page: demo research capabilities
// ---------------------------------------------------------------------------
function pageSkills() {
  const wrap = el("div", "panel");
  wrap.appendChild(screenTitle("07", "研究能力", "以用户语言说明专家团队可使用的专业分析方法。"));
  const list = el("div", "report-list");
  DEMO_SKILLS.forEach((skill) => {
    const method = publicResearchMethod(skill);
    const item = el("div", "report-item");
    item.style.cursor = "default";
    item.appendChild(el("span", "ri-ico", "🧩"));
    item.appendChild(el("div", "", `
      <div style="font-weight:600">${esc(method.name)} <span class="badge online"><span class="dot ok"></span>可用</span></div>
      <div style="color:var(--text-2);font-size:12px;margin-top:3px">${esc(method.description)}</div>
    `));
    list.appendChild(item);
  });
  wrap.appendChild(list);
  return wrap;
}

// ===========================================================================
// LIVE pages — bound to the real backend read-only API (mode === "live")
// ===========================================================================
let liveExpertSel = null;
let liveExpertTab = "cap";
let liveExpertQuery = "";

// ---- live: experts center -------------------------------------------------
function pageExpertsLive() {
  const host = el("div");
  return renderLive(host, fetchExperts, (experts) => buildExpertsLive(experts));
}

function buildExpertsLive(experts) {
  if (!liveExpertSel || !experts.some((e) => e.id === liveExpertSel)) {
    liveExpertSel = experts.length ? experts[0].id : null;
  }
  const layout = el("div", "experts-layout");
  const left = el("div", "panel");
  left.appendChild(screenTitle("04", "专家中心", "了解每位投研专家的专业分工、研究能力和当前可用状态。"));

  const toolbar = el("div", "experts-toolbar");
  const search = el("input");
  search.type = "text";
  search.placeholder = "🔍 搜索专家或能力…";
  search.value = liveExpertQuery;
  const grid = el("div", "experts-grid");
  search.addEventListener("input", () => { liveExpertQuery = search.value; drawGrid(); });
  toolbar.append(search);
  left.appendChild(toolbar);
  left.appendChild(grid);

  const foot = el("div", "experts-foot");
  const enabledN = experts.filter((e) => e.enabled).length;
  foot.innerHTML = `<span>共 ${experts.length} 位专家</span>
    <span><span class="dot ok"></span>启用 ${enabledN}</span>
    <span><span class="dot"></span>停用 ${experts.length - enabledN}</span>`;
  left.appendChild(foot);
  layout.appendChild(left);

  const detail = el("div", "panel");
  detail.id = "liveExpertDetail";
  layout.appendChild(detail);

  function drawGrid() {
    grid.innerHTML = "";
    const q = liveExpertQuery.trim();
    experts
      .filter((e) => {
        if (!q) return true;
        const hay = `${e.name} ${e.role} ${e.specialty} ${publicAgentCapabilities(e).join(" ")} ${publicAgentMethods(e).map((item) => item.name).join(" ")}`;
        return hay.includes(q);
      })
      .forEach((e) => {
        const card = el("button", `expert-card${e.id === liveExpertSel ? " sel" : ""}${e.enabled ? "" : " off"}`);
        card.appendChild(avatar(e.id, 64, "ec-ava"));
        card.appendChild(el("strong", "", esc(e.name)));
        card.appendChild(el("div", "", `<span style="color:var(--text-2);font-size:11.5px">${esc(e.role)}</span> <span class="badge ${e.status}"><span class="dot"></span>${statusText(e.status)}</span>`));
        card.appendChild(el("div", "ec-spec", esc(e.specialty)));
        card.appendChild(el("div", "ec-desc", `研究能力 <b style="color:var(--cyan)">${publicAgentCapabilities(e).length}</b> 项 · 分析方法 <b style="color:var(--cyan)">${publicAgentMethods(e).length}</b> 项`));
        card.appendChild(el("div", "ec-desc", esc(safePublicText(e.description, "负责本次研究中对应的专业分析与证据核查。"))));
        card.addEventListener("click", () => { liveExpertSel = e.id; liveExpertTab = "cap"; drawGrid(); drawDetail(); });
        grid.appendChild(card);
      });
  }

  function drawDetail() {
    const panel = detail;
    const e = experts.find((x) => x.id === liveExpertSel);
    panel.innerHTML = "";
    if (!e) { panel.appendChild(stateBox("empty", "暂无专家数据")); return; }

    const head = el("div", "detail-head");
    head.appendChild(avatar(e.id, 74, "pix-ava dh-ava"));
    const hinfo = el("div");
    hinfo.style.flex = "1";
    hinfo.innerHTML = `<div style="font-size:20px;font-weight:700">${esc(e.name)}</div>
      <div style="color:var(--text-2);font-size:12.5px">${esc(e.role)} <span class="badge ${e.status}"><span class="dot"></span>${statusText(e.status)}</span></div>`;
    head.appendChild(hinfo);
    panel.appendChild(head);
    panel.appendChild(el("p", "", `<span style="color:var(--text-2);line-height:1.7">${esc(safePublicText(e.description, "负责本次研究中对应的专业分析与证据核查。"))}</span>`));

    const tabs = el("div", "tabs");
    [["cap", "研究能力"], ["skills", "分析方法"], ["config", "配置管理"]].forEach(([k, t]) => {
      const tab = el("button", `tab${liveExpertTab === k ? " active" : ""}`, esc(t));
      tab.addEventListener("click", () => { liveExpertTab = k; drawDetail(); });
      tabs.appendChild(tab);
    });
    panel.appendChild(tabs);

    const body = el("div");
    panel.appendChild(body);

    if (liveExpertTab === "cap") {
      const capabilities = publicAgentCapabilities(e);
      body.appendChild(el("div", "follow-sec-title", `研究能力 · ${capabilities.length} 项`));
      if (capabilities.length) {
        const tagwrap = el("div"); tagwrap.style.cssText = "display:flex;flex-wrap:wrap;gap:8px";
        capabilities.forEach((c) => tagwrap.appendChild(el("span", "badge", esc(c))));
        body.appendChild(tagwrap);
      } else body.appendChild(el("div", "op-note", "该专家的公开能力说明正在完善。"));
    } else if (liveExpertTab === "skills") {
      const methods = publicAgentMethods(e);
      body.appendChild(el("div", "follow-sec-title", `专业分析方法 · ${methods.length} 项`));
      if (methods.length) methods.forEach((method) => {
        const row = el("div", "skill-row");
        row.innerHTML = `<span>🧩</span><span><strong>${esc(method.name)}</strong><small style="display:block;color:var(--text-2);margin-top:3px">${esc(method.description)}</small></span>`;
        body.appendChild(row);
      });
      else body.appendChild(el("div", "op-note", "该专家当前没有对外展示的分析方法。"));
    } else if (liveExpertTab === "config") {
      const enable = el("div", "op-enable");
      enable.innerHTML = `<div><strong>启用该专家</strong><div class="op-note">停用后，研究经理将不再把该专家纳入后续任务。设置实时生效。</div></div>`;
      const sw = el("button", `switch${e.enabled ? " on" : ""}`);
      sw.addEventListener("click", () => {
        const next = !e.enabled;
        sw.classList.toggle("on", next);
        liveSetExpertEnabled(e.id, next)
          .then((info) => {
            e.enabled = info.enabled;
            e.status = info.enabled ? "online" : "off";
            toast(`${e.name} 已${e.enabled ? "启用" : "停用"}`);
            drawGrid();
            drawDetail();
          })
          .catch((err) => {
            sw.classList.toggle("on", e.enabled);
            toast("操作未完成：研究服务暂时无法接受本次设置，请稍后重试。");
          });
      });
      enable.appendChild(sw);
      body.appendChild(enable);
    }
  }

  drawGrid();
  drawDetail();
  return layout;
}

// ---- live: research capabilities ------------------------------------------
function pageSkillsLive() {
  const host = el("div");
  return renderLive(host, fetchSkills, (skills) => {
    const wrap = el("div", "panel");
    wrap.appendChild(screenTitle("07", "研究能力", "了解专家团队可使用的专业研究方法，以及每种方法帮助用户回答什么问题。"));
    if (!skills.length) {
      wrap.appendChild(stateBox("empty", "暂无可展示的研究能力", "研究服务仍可保留已完成的报告，请稍后再查看能力清单。"));
      return wrap;
    }
    const list = el("div", "report-list");
    skills.forEach((s) => {
      const method = publicResearchMethod(s);
      const item = el("div", "report-item");
      item.style.cursor = "default";
      item.appendChild(el("span", "ri-ico", "📘"));
      item.appendChild(el("div", "", `
        <div style="font-weight:600">${esc(method.name)} <span class="badge ${s.enabled ? "online" : ""}"><span class="dot ${s.enabled ? "ok" : ""}"></span>${s.enabled ? "当前可用" : "当前未开放"}</span></div>
        <div style="color:var(--text-2);font-size:12px;margin-top:3px">${esc(method.description)}</div>
      `));
      list.appendChild(item);
    });
    wrap.appendChild(list);
    return wrap;
  });
}

// ---- live: tasks center ---------------------------------------------------
function pageTasksLive() {
  const host = el("div");
  return renderLive(host, () => Promise.all([fetchTasks(), fetchReports()]), ([tasks, reports]) => {
    const wrap = el("div", "panel");
    wrap.appendChild(el("div", "panel-title", "历史记录 <span class='title-extra'>报告与任务</span>"));
    if (!tasks.length && !reports.length) {
      wrap.appendChild(stateBox("empty", "暂无历史记录", "从投研大厅完成研究后，报告和任务记录会保存在这里。"));
      return wrap;
    }
    if (reports.length) {
      wrap.appendChild(el("div", "follow-sec-title", "历史报告"));
      const reportList = el("div", "report-list");
      reports.forEach((r) => {
        const publicTitle = researchPresentation
          ? researchPresentation.publicText(r.title, "未命名研究报告")
          : r.title;
        const item = el("button", "report-item");
        item.appendChild(el("span", "ri-ico", "📄"));
        const ratio = r.completeness ? Math.round((r.completeness.completion_ratio || 0) * 100) : null;
        item.appendChild(el("div", "", `
          <div style="font-weight:600">${esc(publicTitle)}</div>
          <div style="color:var(--text-2);font-size:12px;margin-top:3px">${esc(r.created_at)} · 真实研究结果</div>
        `));
        if (ratio != null) item.appendChild(el("div", "ri-score", `<strong>${ratio}%</strong><span style="color:var(--text-2);font-size:11px">完成度</span>`));
        item.addEventListener("click", () => navigate("reports", r.id));
        reportList.appendChild(item);
      });
      wrap.appendChild(reportList);
    }
    if (!tasks.length) return wrap;
    wrap.appendChild(el("div", "follow-sec-title", "历史任务"));
    const list = el("div", "task-list");
    tasks.forEach((t) => {
      const item = el("div", "task-item");
      item.appendChild(el("span", "ri-ico", "📄"));
      const dur = t.duration_ms != null ? ` · ${(t.duration_ms / 1000).toFixed(1)}s` : "";
      const status = {
        completed: "已完成",
        partially_completed: "部分完成",
        failed: "无法完成",
        running: "研究中",
        needs_clarification: "等待补充信息",
      }[t.status] || "等待研究";
      const prompt = researchPresentation
        ? researchPresentation.publicText(t.prompt)
        : t.prompt;
      item.appendChild(el("div", "", `<div class="ti-title">${esc(prompt.slice(0, 60) || "未命名研究任务")}</div><div class="ti-sub">${esc(status)} · ${esc(t.created_at)}${esc(dur)}</div>`));
      list.appendChild(item);
    });
    wrap.appendChild(list);
    return wrap;
  });
}

// ---- live: reports list ---------------------------------------------------
function pageReportListLive() {
  const host = el("div");
  const loadCurrentReport = async () => {
    if (currentReportId) {
      try {
        return await fetchReport(currentReportId);
      } catch (_) {
        rememberCurrentReport(null);
      }
    }
    if (liveSession.prompt && liveSession.phase !== "idle") return null;
    const reports = await fetchReports();
    if (!reports.length) return null;
    rememberCurrentReport(reports[0].id);
    return fetchReport(reports[0].id);
  };
  return renderLive(host, loadCurrentReport, (report) => {
    if (report) return buildReportDetailLive(report);
    const wrap = el("div", "panel");
    const running = liveSession.prompt && liveSession.phase !== "idle";
    wrap.appendChild(stateBox(
      "empty",
      running ? "本次研究报告正在生成" : "暂无当前研究报告",
      running
        ? "Multi-Agent 完成研究后会自动跳转到本次报告。"
        : "完成一次研究后，最新报告会在这里直接打开；历史报告请前往历史记录。",
    ));
    return wrap;
  });
}

// ---- live: report detail + coach sidebar (陪练问答 + 证据检索双通道) ------
function pageReportDetailLive(reportId) {
  const host = el("div");
  return renderLive(host, () => fetchReport(reportId), buildReportDetailLive);
}

function buildReportDetailLive(report) {
  const layout = el("div", "report-layout");
  const main = buildReportMainLive(report);
  layout.appendChild(main);
  const coach = buildCoachSidebar({
    seedMessages: report.coach_messages || [],
    sectionContexts: main.reportNavigation || [],
    loadGuide: (refresh) => fetchCoachGuide(report.id, refresh),
    ask: (question, quoted) => askCoach(report.id, question, quoted),
    evidence: (question) => submitReportFollowup(report.id, question),
    onCollapseChange: (c) => layout.classList.toggle("coach-collapsed", c),
  });
  layout.appendChild(coach.root);
  const reading = wireReportReading(main, coach);
  // 选字引用：报告正文选区 → 侧边栏引用 chip（导航离开时清理监听）
  const quoting = attachSelectionQuoting(main, (text) => coach.setQuote(text));
  registerTeardown(() => {
    reading.destroy();
    quoting.destroy();
  });
  extractReportGlossary(report.id)
    .then((terms) => registerGlossaryTerms(terms, layout))
    .catch(() => {});
  return layout;
}

function buildReportMainLive(report) {
  const col = el("div", "glossary-scope research-report final-report");
  const toolbar = el("div", "rpt-toolbar");
  const back = el("button", "btn-ghost", "‹ 返回历史记录");
  back.addEventListener("click", () => navigate("tasks"));
  toolbar.appendChild(back);
  toolbar.appendChild(el(
    "span",
    "research-truth-label",
    report.demo ? "产品演示报告 · 本地示例" : "仅展示本次真实研究",
  ));
  col.appendChild(toolbar);

  if (!researchPresentation) {
    col.appendChild(stateBox(
      "error",
      "结果展示模块未能加载",
      "研究结果仍被保留，但当前无法安全地转换为用户可见报告。",
    ));
    return col;
  }

  const vm = researchPresentation.buildResearchViewModel({
    report,
    task: report.task,
  });
  if (vm.empty) {
    col.appendChild(stateBox(
      "empty",
      "本次任务尚未形成可展示结果",
      "当前任务还没有生成可展示的研究内容。",
    ));
    return col;
  }
  col.reportNavigation = compactReportNavigation(vm);
  col.appendChild(renderReportNavigation(col.reportNavigation));
  const hero = renderResearchHero(report, vm);
  hero.id = "report-overview";
  hero.dataset.reportSection = "report-overview";
  col.appendChild(hero);
  connectReportKnowledge(vm.metrics);
  if (vm.finalSummary.evidence.length) {
    col.appendChild(withReportSection(renderFinalEvidence(vm.finalSummary.evidence), "report-key-evidence"));
  }
  col.appendChild(withReportSection(renderMetricOverview(vm.metrics), "report-key-metrics"));
  col.appendChild(withReportSection(renderSignals(vm), "report-synthesis"));
  if (vm.learningSummary.evidenceBoundary.length) {
    col.appendChild(renderDynamicEvidenceBoundary(vm));
  }
  col.appendChild(renderCompactLearningQuiz(vm.learningSummary));
  col.appendChild(renderEvidenceTraceDrawer(vm));
  if (vm.disclaimer) col.appendChild(el("div", "op-note research-disclaimer", esc(vm.disclaimer)));
  return col;
}

function compactReportNavigation(vm) {
  const items = [
    { id: "report-overview", label: "结论" },
    vm.finalSummary.evidence.length ? { id: "report-key-evidence", label: "证据" } : null,
    { id: "report-key-metrics", label: "指标" },
    { id: "report-synthesis", label: "风险" },
    vm.learningSummary.evidenceBoundary.length ? { id: "report-evidence-boundary", label: "边界" } : null,
    { id: "report-learning-quiz", label: "学习检查" },
    { id: "report-evidence-trace", label: "追溯" },
  ].filter(Boolean);
  const seen = new Set();
  return items.filter((item) => {
    if (seen.has(item.id)) return false;
    seen.add(item.id);
    return true;
  });
}

function withReportSection(node, id) {
  node.id = id;
  node.dataset.reportSection = id;
  return node;
}

function renderCompactLearningQuiz(summary) {
  const panel = researchPanel(
    "LEARNING CHECK",
    "做一道题，确认你真的看懂了",
    "用本次报告里的指标和证据边界做一次快速检查。",
    "compact-learning-check",
  );
  panel.id = "report-learning-quiz";
  panel.dataset.reportSection = panel.id;
  if (summary.quiz) panel.appendChild(renderLearningQuiz(summary.quiz));
  return panel;
}

function renderEvidenceTraceDrawer(vm) {
  const panel = researchPanel(
    "TRACE",
    "研究过程与证据追溯",
    "默认收起。需要审计结论、复盘专家分工或查看数据覆盖时再展开。",
    "evidence-trace-section",
  );
  panel.id = "report-evidence-trace";
  panel.dataset.reportSection = panel.id;
  const details = el("details", "research-details trace-drawer");
  const summary = el("summary", "");
  summary.appendChild(el("strong", "", "展开完整追溯内容"));
  summary.appendChild(el("span", "", "专家、研究框架、证据链、工作台、数据覆盖与学习总结"));
  details.appendChild(summary);
  const body = el("div", "trace-drawer-body");
  body.appendChild(renderResearchTrace(vm));
  (vm.chapters || []).forEach((chapter) => body.appendChild(renderDynamicAgentChapter(chapter)));
  body.appendChild(renderParticipants(vm));
  body.appendChild(renderResearchPlan(vm.researchPlan));
  body.appendChild(renderEvidenceChains(vm.evidenceChains));
  body.appendChild(renderAgentWorkbenches(vm.agents));
  body.appendChild(renderCoverage(vm.coverage));
  if (
    vm.learningSummary.framework.length
    || vm.learningSummary.terms.length
    || vm.learningSummary.professionalQuestions.length
  ) {
    body.appendChild(renderDynamicLearningSummary(vm.learningSummary, { includeQuiz: false }));
  }
  isolateTraceDrawerSections(body);
  details.appendChild(body);
  panel.appendChild(details);
  return panel;
}

function isolateTraceDrawerSections(root) {
  root.querySelectorAll("[data-report-section]").forEach((section) => {
    section.removeAttribute("data-report-section");
  });
}

function renderReportNavigation(items) {
  const nav = el("nav", "report-section-nav");
  nav.setAttribute("aria-label", "本次报告章节");
  const progress = el("div", "report-reading-progress");
  const track = el("span", "report-reading-progress-track");
  track.appendChild(el("i", "report-reading-progress-fill"));
  progress.append(
    el("span", "report-reading-progress-label", "阅读进度 0%"),
    track,
  );
  const links = el("div", "report-section-nav-links");
  (items || []).forEach((item, index) => {
    const button = el("button", `report-section-link${index === 0 ? " active" : ""}`, esc(item.label));
    button.type = "button";
    button.dataset.sectionTarget = item.id;
    if (index === 0) button.setAttribute("aria-current", "true");
    links.appendChild(button);
  });
  nav.append(progress, links);
  return nav;
}

function renderResearchTrace(vm) {
  const trace = el("div", "research-trace");
  const questions = vm.researchPlan?.researchQuestions || [];
  if (questions.length) {
    const path = el("div", "research-trace-block");
    path.appendChild(el("strong", "", "本次研究路径"));
    const list = el("ol", "research-trace-list");
    questions.forEach((item) => {
      const row = el("li");
      row.appendChild(el("span", "", esc(item.question)));
      row.appendChild(el("small", "", esc(item.role)));
      list.appendChild(row);
    });
    path.appendChild(list);
    trace.appendChild(path);
  }
  if (vm.participation?.length) {
    const team = el("div", "research-trace-block research-trace-team");
    team.appendChild(el("strong", "", "实际参与"));
    const tags = el("div", "research-trace-tags");
    vm.participation.forEach((item) => {
      tags.appendChild(el("span", "", esc(item.role)));
    });
    team.appendChild(tags);
    trace.appendChild(team);
  }
  return trace;
}

function teachingSection(title, items, cls = "") {
  const values = (items || []).filter((item) => {
    const text = typeof item === "string" ? item : item?.text;
    return Boolean(text);
  });
  if (!values.length) return null;
  const section = el("section", `teaching-block ${cls}`.trim());
  section.appendChild(el("h3", "", esc(title)));
  section.appendChild(researchList(values));
  return section;
}

function renderDynamicAgentChapter(agent) {
  const panel = researchPanel(
    agent.role,
    agent.title,
    agent.researchQuestion,
    "dynamic-agent-chapter",
  );
  panel.id = agent.sectionId;
  panel.dataset.reportSection = agent.sectionId;

  const boundaries = agent.boundaries?.length
    ? agent.boundaries
    : ["本节结论只覆盖上方已经展示的事实、数据与研究范围。"];
  const facts = agent.facts?.length
    ? agent.facts
    : ["本节没有返回可单独展示的事实或数值，因此不把专业判断改写成数据。"];
  const methods = agent.methods?.length
    ? agent.methods
    : ["本次结果未单独记录可展示的分析方法，页面不补造方法说明。"];
  const reasoning = agent.interpretations?.length
    ? agent.interpretations
    : ["本次结果未返回可单独展示的判断，页面仅保留已有研究边界。"];
  const misconceptions = agent.misconceptions?.length
    ? agent.misconceptions.map((item) =>
      `误区：${item.wrong}。正确边界：${item.correct}`
    )
    : ["不要把本节的阶段性判断扩大到已展示证据之外。"];
  const nextChecks = agent.nextChecks?.length
    ? agent.nextChecks
    : boundaries.map((item) => `继续补充能够验证“${item}”的真实证据。`);
  const blocks = [
    teachingSection("本节研究什么", [agent.researchQuestion], "teaching-question"),
    teachingSection("事实与数据", facts, "teaching-facts"),
    teachingSection("使用了什么分析方法", methods, "teaching-methods"),
    teachingSection("为什么得出这个判断", reasoning, "teaching-reasoning"),
    teachingSection("这个结论不能说明什么", boundaries, "teaching-boundary"),
    teachingSection("常见误区", misconceptions, "teaching-mistake"),
    teachingSection("下一步如何验证", nextChecks, "teaching-next"),
  ].filter(Boolean);
  const grid = el("div", "teaching-grid");
  blocks.forEach((block) => grid.appendChild(block));
  panel.appendChild(grid);
  panel.appendChild(renderSectionCoachCard(agent, misconceptions[0]));
  return panel;
}

function renderSectionCoachCard(agent, fallbackMisconception) {
  const card = el("aside", "section-coach-card");
  const head = el("div", "section-coach-card-head");
  head.appendChild(el("span", "section-coach-avatar", "教"));
  head.appendChild(el("div", "", "<strong>陪练解读</strong><small>跟着专业研究者读这一节</small>"));
  card.appendChild(head);
  const rows = [
    ["专业人员在看什么", [
      agent.researchQuestion,
      ...(agent.metrics || []).slice(0, 3).map((metric) => metric.label),
    ].filter(Boolean).join("；")],
    ["用户应该记住什么", agent.coach?.oneLine || agent.interpretations?.[0]],
    ["最容易犯的错误", agent.coach?.misconception || fallbackMisconception],
  ].filter(([, value]) => value);
  const body = el("div", "section-coach-card-body");
  rows.forEach(([label, value]) => {
    const row = el("div", "section-coach-card-row");
    row.appendChild(el("strong", "", esc(label)));
    row.appendChild(el("p", "", esc(value)));
    body.appendChild(row);
  });
  card.appendChild(body);
  return card;
}

function renderDynamicEvidenceBoundary(vm) {
  const panel = researchPanel(
    "证据边界",
    "风险、限制与数据范围",
    "只展示本次真实结果中已经出现的风险、缺口和覆盖范围。",
    "dynamic-boundary-section",
  );
  panel.id = "report-evidence-boundary";
  panel.dataset.reportSection = panel.id;
  const grid = el("div", "dynamic-boundary-grid");
  if (vm.riskSignals.length) {
    grid.appendChild(teachingSection("需要关注的风险", vm.riskSignals, "real-risk"));
  }
  if (vm.limitations.length) {
    grid.appendChild(teachingSection("结论限制", vm.limitations));
  }
  const coverage = (vm.coverage || [])
    .filter((item) => item.status !== "available")
    .map((item) => `${item.type}：${item.impact}`);
  if (coverage.length) {
    grid.appendChild(teachingSection("数据范围", coverage));
  }
  const remaining = vm.learningSummary.evidenceBoundary.filter((item) =>
    !vm.riskSignals.includes(item)
    && !vm.limitations.includes(item)
    && !coverage.some((text) => text.includes(item))
  );
  if (remaining.length) {
    grid.appendChild(teachingSection("仍需验证", remaining));
  }
  panel.appendChild(grid);
  return panel;
}

function renderDynamicLearningSummary(summary, options = {}) {
  const includeQuiz = options.includeQuiz !== false;
  const panel = researchPanel(
    "学习总结",
    "把这次研究方法带到下一次",
    "以下总结仅由本次实际研究路径、术语、证据边界和后续问题组成。",
    "dynamic-learning-summary",
  );
  panel.id = "report-learning-summary";
  panel.dataset.reportSection = panel.id;
  const grid = el("div", "dynamic-learning-grid");
  if (summary.framework.length) {
    grid.appendChild(teachingSection("本次可复用的研究框架", summary.framework));
  }
  if (summary.terms.length) {
    const terms = el("section", "teaching-block learning-terms-block");
    terms.appendChild(el("h3", "", "本次涉及的专业术语"));
    const wrap = el("div", "learning-terms");
    summary.terms.forEach((term) => wrap.appendChild(el("span", "", esc(term))));
    terms.appendChild(wrap);
    grid.appendChild(terms);
  }
  if (summary.evidenceBoundary.length) {
    grid.appendChild(teachingSection("本次结论的证据边界", summary.evidenceBoundary));
  }
  if (summary.professionalQuestions.length) {
    grid.appendChild(teachingSection(
      "下次可以提出的更专业问题",
      summary.professionalQuestions,
      "learning-question-block",
    ));
  }
  panel.appendChild(grid);
  if (includeQuiz && summary.quiz) {
    panel.appendChild(renderLearningQuiz(summary.quiz));
  }
  return panel;
}

function wireReportReading(main, coach) {
  let destroyed = false;
  let connection = { destroy() {} };
  const frame = requestAnimationFrame(() => {
    if (!destroyed) connection = connectReportReading(main, coach);
  });
  return {
    destroy() {
      destroyed = true;
      cancelAnimationFrame(frame);
      connection.destroy();
    },
  };
}

function connectReportReading(main, coach) {
  const nav = main.querySelector(".report-section-nav");
  const sections = [...main.querySelectorAll("[data-report-section]")];
  const buttons = [...main.querySelectorAll("[data-section-target]")];
  const progressFill = main.querySelector(".report-reading-progress-fill");
  const progressLabel = main.querySelector(".report-reading-progress-label");
  const scrollRoot = main.closest(".page-outlet");
  if (!nav || !sections.length || !scrollRoot) {
    return { destroy() {} };
  }

  const activate = (id) => {
    buttons.forEach((button) => {
      const active = button.dataset.sectionTarget === id;
      button.classList.toggle("active", active);
      if (active) button.setAttribute("aria-current", "true");
      else button.removeAttribute("aria-current");
    });
    coach?.setContext?.(id);
  };

  const onClick = (event) => {
    const button = event.currentTarget;
    const target = main.querySelector(`#${CSS.escape(button.dataset.sectionTarget)}`);
    if (!target) return;
    activate(button.dataset.sectionTarget);
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  buttons.forEach((button) => button.addEventListener("click", onClick));

  const updateProgress = () => {
    const rootRect = scrollRoot.getBoundingClientRect();
    const mainRect = main.getBoundingClientRect();
    const readable = Math.max(1, main.scrollHeight - rootRect.height * 0.7);
    const read = Math.max(0, rootRect.top + rootRect.height * 0.2 - mainRect.top);
    const percent = Math.max(0, Math.min(100, Math.round((read / readable) * 100)));
    if (progressFill) progressFill.style.width = `${percent}%`;
    if (progressLabel) progressLabel.textContent = `阅读进度 ${percent}%`;

    const marker = rootRect.top + Math.min(180, rootRect.height * 0.24);
    let current = sections[0];
    sections.forEach((section) => {
      if (section.getBoundingClientRect().top <= marker) current = section;
    });
    activate(current.id);
  };
  scrollRoot.addEventListener("scroll", updateProgress, { passive: true });

  const observer = new IntersectionObserver((entries) => {
    const visible = entries
      .filter((entry) => entry.isIntersecting)
      .sort((left, right) => right.intersectionRatio - left.intersectionRatio);
    if (visible[0]) activate(visible[0].target.id);
  }, {
    root: scrollRoot,
    rootMargin: "-18% 0px -62% 0px",
    threshold: [0.05, 0.25, 0.6],
  });
  sections.forEach((section) => observer.observe(section));
  requestAnimationFrame(updateProgress);

  return {
    destroy() {
      observer.disconnect();
      scrollRoot.removeEventListener("scroll", updateProgress);
      buttons.forEach((button) => button.removeEventListener("click", onClick));
    },
  };
}

function connectReportKnowledge(metrics) {
  const glossary = globalThis.AlphaGlossary;
  if (!glossary?.setResearchEntries) return 0;
  return glossary.setResearchEntries((metrics || []).map((metric) => ({
    term: metric.label,
    color: "var(--cyan)",
    explanation: [
      metric.english
        ? `${metric.english}${metric.abbreviation ? `（${metric.abbreviation}）` : ""}。`
        : "",
      metric.purpose,
      metric.importance,
      metric.formula ? `计算方式：${metric.formula}。` : "",
      `本次结果：${metric.value}${metric.subject ? `（${metric.subject}）` : ""}。`,
      metric.reading,
      `使用局限：${metric.limitation}`,
      `建议结合：${metric.combineWith}。`,
    ].filter(Boolean).join(" "),
  })));
}

function researchPanel(kicker, title, description, cls = "") {
  const panel = el("section", `panel research-section ${cls}`.trim());
  const head = el("div", "research-section-head");
  head.appendChild(el("span", "research-kicker", esc(kicker)));
  const copy = el("div");
  copy.appendChild(el("h2", "", esc(title)));
  if (description) copy.appendChild(el("p", "", esc(description)));
  head.appendChild(copy);
  panel.appendChild(head);
  return panel;
}

function researchList(items, cls = "") {
  const list = el("div", `research-list ${cls}`.trim());
  const values = (items || []).filter(Boolean);
  if (!values.length) {
    list.appendChild(el("p", "research-empty", "本次结果没有返回这一层内容，因此不补写固定教材。"));
    return list;
  }
  values.forEach((item) => {
    const text = typeof item === "string" ? item : item.text;
    if (!text) return;
    const row = el("div", "research-list-item");
    row.appendChild(el("span", "research-list-mark", ""));
    row.appendChild(el("span", "", esc(text)));
    list.appendChild(row);
  });
  return list;
}

function renderResearchHero(report, vm) {
  const hero = el("section", "panel research-hero");
  const eyebrow = el("div", "research-hero-eyebrow");
  eyebrow.appendChild(el("span", "research-live-dot", ""));
  eyebrow.appendChild(el("span", "", "最终直接回答"));
  eyebrow.appendChild(el("span", "research-created", esc(report.created_at || "")));
  hero.appendChild(eyebrow);
  hero.appendChild(el("h1", "", esc(vm.finalSummary.conclusion.headline)));
  if (vm.finalSummary.conclusion.explanation) {
    hero.appendChild(el(
      "p",
      "research-hero-explanation",
      esc(vm.finalSummary.conclusion.explanation),
    ));
  }
  const badges = el("div", "research-summary-badges");
  badges.appendChild(el(
    "span",
    "research-badge",
    `判断倾向 · ${esc(vm.finalSummary.conclusion.stance)}`,
  ));
  badges.appendChild(el(
    "span",
    "research-badge",
    `置信程度 · ${esc(vm.finalSummary.conclusion.confidence)}`,
  ));
  hero.appendChild(badges);
  return hero;
}

function renderFinalEvidence(evidence) {
  const panel = researchPanel("KEY EVIDENCE", "关键证据", "");
  const list = el("div", "final-evidence-list");
  evidence.forEach((item) => {
    const card = el("article", "final-evidence-card");
    card.appendChild(el("strong", "", esc(item.title)));
    if (item.explanation) card.appendChild(el("p", "", esc(item.explanation)));
    list.appendChild(card);
  });
  panel.appendChild(list);
  return panel;
}

function renderFinalList(kicker, title, items, cls) {
  const panel = researchPanel(kicker, title, "", cls);
  panel.appendChild(researchList(items));
  return panel;
}

function renderFinalLearning(focus) {
  const panel = researchPanel("LEARNING FOCUS", "本次分析方法", "");
  const card = el("div", "final-learning-card");
  card.appendChild(el("h3", "", esc(focus.title)));
  const steps = el("ol", "final-method-steps");
  focus.methods.forEach((item) => steps.appendChild(el("li", "", esc(item))));
  card.appendChild(steps);
  if (focus.misconception) {
    card.appendChild(el(
      "p",
      "final-common-mistake",
      `<span>常见误区</span>${esc(focus.misconception)}`,
    ));
  }
  panel.appendChild(card);
  return panel;
}

function renderParticipants(vm) {
  const panel = researchPanel(
    "01 · EXPERT TEAM",
    "本次参与的专家",
    "只列出本次任务实际选择且产生执行结果的专家。",
  );
  const grid = el("div", "participant-grid");
  if (!vm.participation.length) {
    grid.appendChild(el("p", "research-empty", "本次任务没有实际完成的专家结果。"));
  }
  vm.participation.forEach((item) => {
    const card = el("article", "participant-card");
    card.appendChild(el("span", "participant-avatar", esc(item.name.slice(0, 1))));
    const body = el("div");
    body.appendChild(el("strong", "", esc(item.name)));
    body.appendChild(el("small", "", esc(item.role)));
    body.appendChild(el("p", "", esc(item.contribution)));
    card.appendChild(body);
    card.appendChild(el("span", "research-status completed", esc(item.status)));
    grid.appendChild(card);
  });
  panel.appendChild(grid);
  return panel;
}

function renderResearchPlan(plan) {
  const panel = researchPanel(
    "02 · RESEARCH PLAN",
    "研究问题与分析框架",
    "研究经理如何把原始问题拆成可验证的专业子问题。",
  );
  const question = el("div", "original-question");
  question.appendChild(el("span", "", "用户原始问题"));
  question.appendChild(el("strong", "", esc(plan.originalQuestion || plan.goal)));
  if (plan.goal && plan.goal !== plan.originalQuestion) {
    question.appendChild(el("p", "", `研究目标：${esc(plan.goal)}`));
  }
  panel.appendChild(question);

  const steps = el("div", "research-plan-steps");
  plan.researchQuestions.forEach((item) => {
    const step = el("article", "research-plan-step");
    step.appendChild(el("span", "plan-step-number", String(item.order).padStart(2, "0")));
    const body = el("div");
    body.appendChild(el("h3", "", esc(item.question)));
    body.appendChild(el("p", "", `${esc(item.agent)} · ${esc(item.role)}`));
    if (item.output) body.appendChild(el("small", "", `预期形成：${esc(item.output)}`));
    step.appendChild(body);
    steps.appendChild(step);
  });
  if (!plan.researchQuestions.length) {
    steps.appendChild(el("p", "research-empty", "本次任务没有创建专家研究步骤。"));
  }
  panel.appendChild(steps);

  const layout = el("div", "plan-logic-grid");
  const division = el("div", "plan-logic-card");
  division.appendChild(el("h3", "", "为什么需要这些专家"));
  division.appendChild(researchList(plan.agents.map((agent) =>
    `${agent.name}：${agent.reason}`
  )));
  layout.appendChild(division);

  const dependency = el("div", "plan-logic-card");
  dependency.appendChild(el("h3", "", "协作与依赖"));
  const lines = [
    ...plan.dependencies.map((item) =>
      `${item.from} 完成后，由 ${item.to} 继续处理：${item.reason}`
    ),
    ...plan.parallelGroups.map((group) =>
      `可并行研究：${group.join("、")}`
    ),
    `最终汇总：${plan.synthesis}`,
  ];
  dependency.appendChild(researchList(lines));
  layout.appendChild(dependency);
  panel.appendChild(layout);
  return panel;
}

function renderMetricOverview(metrics) {
  const panel = researchPanel(
    "03 · KEY METRICS",
    "核心指标总览",
    "每个数字都可以展开查看用途、公式、报告期、解读方法和局限。",
  );
  const grid = el("div", "metric-learning-grid");
  if (!metrics.length) {
    grid.appendChild(el(
      "p",
      "research-empty",
      "本次结果没有返回可安全展示的指标。",
    ));
  }
  metrics.forEach((metric) => grid.appendChild(renderMetricCard(metric)));
  panel.appendChild(grid);
  return panel;
}

function renderMetricCard(metric) {
  const card = el("article", "metric-learning-card");
  const head = el("div", "metric-learning-head");
  const name = el("div");
  name.appendChild(el("span", "research-tag fact", "计算结果"));
  name.appendChild(el("h3", "", esc(metric.label)));
  if (metric.english) {
    name.appendChild(el(
      "small",
      "",
      `${esc(metric.english)}${metric.abbreviation ? ` · ${esc(metric.abbreviation)}` : ""}`,
    ));
  }
  head.appendChild(name);
  const value = el("div", "metric-learning-value");
  value.appendChild(el("strong", "", esc(metric.value)));
  if (metric.subject) value.appendChild(el("small", "", esc(metric.subject)));
  head.appendChild(value);
  card.appendChild(head);
  card.appendChild(el("p", "metric-meaning", esc(metric.interpretation || metric.reading)));
  const details = el("details", "research-details metric-details");
  details.appendChild(el("summary", "", "怎么算 · 为什么重要"));
  const body = el("div", "details-body");
  body.appendChild(metricDetail("它衡量什么", metric.purpose));
  body.appendChild(metricDetail("为什么重要", metric.importance));
  if (metric.formula) body.appendChild(metricDetail("计算方式", metric.formula));
  body.appendChild(metricDetail("如何理解", metric.reading));
  body.appendChild(metricDetail("常见误区与局限", metric.limitation));
  body.appendChild(metricDetail("需要结合", metric.combineWith));
  details.appendChild(body);
  card.appendChild(details);
  return card;
}

function metricDetail(label, value) {
  const row = el("div", "metric-detail-row");
  row.appendChild(el("span", "", esc(label)));
  row.appendChild(el("p", "", esc(value || "本次结果未提供")));
  return row;
}

function renderEvidenceChains(chains) {
  const panel = researchPanel(
    "04 · EVIDENCE CHAIN",
    "从数据到结论的证据链",
    "重要判断可以回看支持证据、反对证据、缺失证据和当前结论强度。",
  );
  const list = el("div", "evidence-chain-list");
  if (!chains.length) {
    list.appendChild(el("p", "research-empty", "本次任务尚未形成可追溯的重要判断。"));
  }
  chains.forEach((chain) => {
    const card = el("article", "evidence-chain-card");
    const flow = el("div", "evidence-flow");
    flow.appendChild(evidenceNode("事实", chain.facts[0] || "相关事实未单独返回"));
    flow.appendChild(el("span", "evidence-arrow", "↓"));
    flow.appendChild(evidenceNode(
      "计算与解释",
      chain.calculation[0] || chain.supporting[0] || "依据已完成的专家结果综合判断",
    ));
    flow.appendChild(el("span", "evidence-arrow", "↓"));
    flow.appendChild(evidenceNode("专业判断", chain.conclusion, "judgment"));
    card.appendChild(flow);
    const details = el("details", "research-details evidence-details");
    details.appendChild(el("summary", "", "查看依据"));
    const body = el("div", "evidence-detail-grid");
    body.appendChild(evidenceColumn("支持证据", chain.supporting));
    body.appendChild(evidenceColumn("反对与风险证据", chain.opposing));
    body.appendChild(evidenceColumn("缺失证据", chain.missing));
    body.appendChild(evidenceColumn("还需要验证", chain.nextChecks));
    const strength = el("div", "evidence-strength");
    strength.appendChild(el("span", "", "当前结论强度"));
    strength.appendChild(el("strong", "", esc(chain.strength)));
    body.appendChild(strength);
    details.appendChild(body);
    card.appendChild(details);
    list.appendChild(card);
  });
  panel.appendChild(list);
  return panel;
}

function evidenceNode(label, text, kind = "fact") {
  const node = el("div", `evidence-node ${kind}`);
  node.appendChild(el("span", "", esc(label)));
  node.appendChild(el("p", "", esc(text)));
  return node;
}

function evidenceColumn(title, items) {
  const col = el("div", "evidence-column");
  col.appendChild(el("h4", "", esc(title)));
  col.appendChild(researchList(items));
  return col;
}

function renderAgentWorkbenches(agents) {
  const panel = researchPanel(
    "05 · EXPERT WORKBENCH",
    "各专家的研究工作台",
    "默认展示核心事实与阶段判断；按需展开方法、替代解释、质疑和下一步研究。",
    "agent-workbench-section",
  );
  const tabs = el("div", "agent-workbench-tabs");
  const body = el("div", "agent-workbench-body");
  if (!agents.length) {
    body.appendChild(el("p", "research-empty", "本次任务没有实际选择专家。"));
    panel.append(tabs, body);
    return panel;
  }
  let active = 0;
  const draw = () => {
    tabs.innerHTML = "";
    body.innerHTML = "";
    agents.forEach((agent, index) => {
      const tab = el("button", `workbench-tab${index === active ? " active" : ""}`);
      tab.type = "button";
      tab.appendChild(el("span", "", esc(agent.name.slice(0, 1))));
      tab.appendChild(el("strong", "", esc(agent.name)));
      tab.appendChild(el("em", `research-status ${agent.status}`, esc(agent.statusLabel)));
      tab.addEventListener("click", () => { active = index; draw(); });
      tabs.appendChild(tab);
    });
    body.appendChild(renderAgentWorkbench(agents[active]));
  };
  draw();
  panel.append(tabs, body);
  return panel;
}

function renderAgentWorkbench(agent) {
  const wrap = el("article", "agent-workbench");
  const hero = el("div", "agent-workbench-hero");
  const copy = el("div");
  copy.appendChild(el("span", "research-kicker", esc(agent.role)));
  copy.appendChild(el("h3", "", esc(agent.researchQuestion)));
  copy.appendChild(el("p", "", esc(agent.reason)));
  hero.appendChild(copy);
  hero.appendChild(el("span", `research-status ${agent.status}`, esc(agent.statusLabel)));
  wrap.appendChild(hero);
  if (agent.emptyReason) {
    wrap.appendChild(el("p", "research-empty", esc(agent.emptyReason)));
    return wrap;
  }

  const dimensions = el("div", "analysis-dimensions");
  agent.analysisDimensions.forEach((item) =>
    dimensions.appendChild(el("span", "", esc(item)))
  );
  wrap.appendChild(dimensions);

  const visible = el("div", "workbench-visible-grid");
  const facts = el("section", "workbench-layer");
  facts.appendChild(el("div", "layer-title", '<span class="research-tag fact">已确认 / 计算</span><strong>关键事实</strong>'));
  facts.appendChild(researchList(agent.facts.slice(0, 5)));
  visible.appendChild(facts);

  const interpretation = el("section", "workbench-layer");
  interpretation.appendChild(el("div", "layer-title", '<span class="research-tag judgment">专业判断</span><strong>阶段性结论</strong>'));
  interpretation.appendChild(researchList(agent.interpretations.slice(0, 4)));
  visible.appendChild(interpretation);

  const pending = el("section", "workbench-layer");
  pending.appendChild(el("div", "layer-title", '<span class="research-tag hypothesis">尚待验证</span><strong>当前证据缺口</strong>'));
  pending.appendChild(researchList([
    ...agent.hypotheses,
    ...agent.nextChecks.slice(0, 2),
  ]));
  visible.appendChild(pending);
  wrap.appendChild(visible);

  const expanders = el("div", "workbench-expanders");
  expanders.appendChild(workbenchDetails(
    "为什么",
    "分析逻辑与指标组合",
    agent.interpretations,
  ));
  expanders.appendChild(workbenchMetricDetails(agent.metrics));
  expanders.appendChild(workbenchTermDetails(agent.terms));
  expanders.appendChild(workbenchDetails(
    "还有哪些可能",
    "替代解释与假设",
    agent.hypotheses,
  ));
  expanders.appendChild(workbenchDetails(
    "挑战这个结论",
    "风险专家会追问什么",
    agent.challenges,
  ));
  expanders.appendChild(workbenchDetails(
    "下一步查什么",
    "专业研究路径",
    agent.nextChecks,
  ));
  expanders.appendChild(workbenchMisconceptions(agent.misconceptions));
  wrap.appendChild(expanders);
  return wrap;
}

function workbenchDetails(label, title, items) {
  const details = el("details", "research-details workbench-details");
  details.appendChild(el("summary", "", esc(label)));
  const body = el("div", "details-body");
  body.appendChild(el("h4", "", esc(title)));
  body.appendChild(researchList(items));
  details.appendChild(body);
  return details;
}

function workbenchMetricDetails(metrics) {
  const details = el("details", "research-details workbench-details");
  details.appendChild(el("summary", "", "怎么算"));
  const body = el("div", "details-body");
  body.appendChild(el("h4", "", "指标计算过程"));
  if (!metrics.length) {
    body.appendChild(el("p", "research-empty", "本次专家结果没有返回可展示的公式。"));
  }
  metrics.forEach((metric) => {
    body.appendChild(metricDetail(
      `${metric.label} · ${metric.value}`,
      metric.formula || "本次结果未返回公式，因此不补造计算过程。",
    ));
  });
  details.appendChild(body);
  return details;
}

function workbenchTermDetails(terms) {
  const details = el("details", "research-details workbench-details");
  details.appendChild(el("summary", "", "学习这个术语"));
  const body = el("div", "details-body");
  if (!terms.length) {
    body.appendChild(el("p", "research-empty", "本次结果没有产生需要单独解释的指标术语。"));
  }
  terms.slice(0, 4).forEach((term) => body.appendChild(metricDetail(
    `${term.label}${term.english ? ` · ${term.english}` : ""}`,
    `${term.purpose} 本次结果：${term.value}。${term.limitation}`,
  )));
  details.appendChild(body);
  return details;
}

function workbenchMisconceptions(items) {
  const details = el("details", "research-details workbench-details misconception-details");
  details.appendChild(el("summary", "", "常见误区"));
  const body = el("div", "details-body");
  if (!items.length) {
    body.appendChild(el("p", "research-empty", "本次结果没有足够的真实局限信息来生成针对性误区提醒。"));
  }
  items.forEach((item) => {
    const card = el("div", "misconception-card");
    card.appendChild(el("strong", "", `不要这样理解：${esc(item.wrong)}`));
    card.appendChild(el("p", "", `正确理解：${esc(item.correct)}`));
    body.appendChild(card);
  });
  details.appendChild(body);
  return details;
}

function renderSignals(vm) {
  const panel = researchPanel(
    "06 · SYNTHESIS",
    "专家观点、积极信号与风险质疑",
    "把支持证据、风险信号、观点冲突和研究局限放在同一层比较。",
  );
  const grid = el("div", "signal-grid");
  grid.appendChild(signalCard("积极信号", vm.positiveSignals, "positive"));
  grid.appendChild(signalCard("需要关注", vm.riskSignals, "risk"));
  grid.appendChild(signalCard(
    "专家观点冲突",
    vm.expertDisagreements.length
      ? vm.expertDisagreements
      : ["本次结果未报告明确冲突；这不代表所有风险已被排除。"],
    "conflict",
  ));
  grid.appendChild(signalCard("研究局限", vm.limitations, "limit"));
  panel.appendChild(grid);
  return panel;
}

function signalCard(title, items, cls) {
  const card = el("article", `signal-card ${cls}`);
  card.appendChild(el("h3", "", esc(title)));
  card.appendChild(researchList(items));
  return card;
}

function renderCoverage(coverage) {
  const panel = researchPanel(
    "07 · DATA COVERAGE",
    "数据覆盖与局限",
    "缺失数据以中性状态解释，并明确它会影响什么判断。",
  );
  const grid = el("div", "coverage-grid");
  if (!coverage.length) {
    grid.appendChild(el(
      "p",
      "research-empty",
      "本次报告没有返回可安全展示的数据覆盖摘要。",
    ));
  }
  coverage.forEach((item) => {
    const card = el("article", `coverage-card ${item.status}`);
    const head = el("div", "coverage-head");
    head.appendChild(el("strong", "", esc(item.type)));
    const label = item.status === "available"
      ? "已获取"
      : item.status === "partial" ? "部分覆盖" : "暂未获取";
    head.appendChild(el("span", `research-status ${item.status}`, esc(label)));
    card.appendChild(head);
    if (item.period) card.appendChild(el("small", "", `覆盖期间：${esc(item.period)}`));
    card.appendChild(el("p", "", esc(item.purpose)));
    card.appendChild(el("p", "coverage-impact", esc(item.impact)));
    grid.appendChild(card);
  });
  panel.appendChild(grid);
  return panel;
}

function renderLearningSummary(summary, knowledgeCount = 0) {
  const panel = researchPanel(
    "08 · LEARNING",
    "本次研究，你掌握了什么？",
    "把本次研究过程还原为可复用的分析框架和专业术语。",
    "learning-section",
  );
  const grid = el("div", "learning-grid");
  const framework = el("article", "learning-card");
  framework.appendChild(el("h3", "", "本次分析框架"));
  framework.appendChild(researchList(summary.framework));
  grid.appendChild(framework);
  const terms = el("article", "learning-card");
  terms.appendChild(el("h3", "", "本次专业术语"));
  const termWrap = el("div", "learning-terms");
  if (!summary.terms.length) {
    termWrap.appendChild(el("p", "research-empty", "本次结果没有产生指标术语。"));
  }
  summary.terms.forEach((term) => termWrap.appendChild(el("span", "", esc(term))));
  terms.appendChild(termWrap);
  if (knowledgeCount) {
    const knowledgeLink = el(
      "button",
      "knowledge-link",
      `📚 ${knowledgeCount} 个本次术语已接入投研知识库`,
    );
    knowledgeLink.type = "button";
    knowledgeLink.addEventListener("click", () => navigate("glossary"));
    terms.appendChild(knowledgeLink);
  }
  grid.appendChild(terms);
  panel.appendChild(grid);
  panel.appendChild(renderLearningQuiz(summary.quiz));
  return panel;
}

function renderLearningQuiz(quiz) {
  const card = el("article", "learning-quiz");
  card.appendChild(el("span", "research-kicker", "学习检查题"));
  card.appendChild(el("h3", "", esc(quiz.question)));
  const options = el("div", "quiz-options");
  const feedback = el("div", "quiz-feedback");
  quiz.options.forEach((option, index) => {
    const button = el("button", "quiz-option");
    button.type = "button";
    button.appendChild(el("span", "", String.fromCharCode(65 + index)));
    button.appendChild(el("strong", "", esc(option)));
    button.addEventListener("click", () => {
      options.querySelectorAll(".quiz-option").forEach((item) => {
        item.disabled = true;
        item.classList.remove("correct", "wrong");
      });
      button.classList.add(index === quiz.answerIndex ? "correct" : "wrong");
      const correct = options.querySelectorAll(".quiz-option")[quiz.answerIndex];
      if (correct) correct.classList.add("correct");
      feedback.className = `quiz-feedback show ${index === quiz.answerIndex ? "correct" : "wrong"}`;
      feedback.textContent = `${index === quiz.answerIndex ? "回答正确。" : "再想一步。"} ${quiz.explanation}`;
    });
    options.appendChild(button);
  });
  card.append(options, feedback);
  return card;
}

function renderOriginalReport(text) {
  const panel = researchPanel(
    "09 · ORIGINAL REPORT",
    "专家整合原文",
    "以下内容来自本次实际运行的报告专家，已过滤内部实现信息。",
  );
  const details = el("details", "research-details original-report");
  details.appendChild(el("summary", "", "展开查看报告原文"));
  details.appendChild(el("div", "original-report-text", esc(text)));
  panel.appendChild(details);
  return panel;
}

// Type-aware renderer for aggregator content blocks. Presentation only: it
// renders exactly the backend evidence, never inventing facts. Unknown shapes
// fall back to the bounded generic walker below.
const BLOCK_ICONS = {
  narrative: "📌", risk_list: "⚠️", action_list: "🎯",
  data_scope: "🗂", limitations: "⛔", key_findings: "✅",
};
function blockIcon(type) {
  return `<span class="blk-ico">${BLOCK_ICONS[type] || "✦"}</span>`;
}

function renderBlock(b) {
  const type = b && b.type;
  const data = (b && b.data) || {};
  if (Array.isArray(data.sources)) return renderDataScope(data.sources);
  if (Array.isArray(data.items) && data.items.length) return renderEvidenceList(data.items, type);
  return renderBlockData(data);
}

const LIST_MARK = {
  narrative: "•", risk_list: "!", action_list: "→", limitations: "∅",
};
function renderEvidenceList(items, type) {
  const list = el("div", `rpt-list rpt-list--${esc(type || "generic")}`);
  items.slice(0, 40).forEach((it) => {
    const text = typeof it === "string" ? it : (it && it.text) || "";
    if (!text) return;
    const li = el("div", "rpt-li");
    li.appendChild(el("span", "rpt-li-mark", esc(LIST_MARK[type] || "•")));
    const body = el("div", "rpt-li-body");
    body.appendChild(el("div", "rpt-li-text", esc(text)));
    li.appendChild(body);
    list.appendChild(li);
  });
  return list;
}

function dataScopeStatus(status) {
  const s = String(status || "");
  if (s === "available") return { cls: "done", label: "数据可用" };
  if (s === "no_data") return { cls: "off", label: "无数据" };
  if (s === "partial") return { cls: "running", label: "部分可用" };
  return { cls: "waiting", label: s || "未知" };
}
function dsKv(k, v, mono) {
  return el("div", "ds-kv", `<span>${esc(k)}</span><b class="${mono ? "mono" : ""}">${esc(String(v))}</b>`);
}
function renderDataScope(sources) {
  const grid = el("div", "ds-cards");
  sources.slice(0, 30).forEach((s) => {
    if (!s || typeof s !== "object") return;
    const item = researchPresentation?.safeObject
      ? researchPresentation.safeObject(s)
      : {};
    const status = dataScopeStatus(s.missing_status);
    const sourceText = JSON.stringify(s).toLowerCase();
    const type = /audit|审计/.test(sourceText)
      ? "审计意见"
      : /forecast|预告/.test(sourceText)
        ? "业绩预告"
        : /financial|fina|财务|利润|营收/.test(sourceText)
          ? "财务报表"
          : /macro|宏观|政策|利率/.test(sourceText)
            ? "宏观与行业数据"
            : /price|market|行情/.test(sourceText)
              ? "历史市场数据"
              : "研究证据";
    const card = el("div", "ds-card");
    const head = el("div", "ds-card-head");
    head.appendChild(el("span", "ds-src", esc(type)));
    head.appendChild(el("span", `badge ${status.cls}`, `<span class="dot"></span>${esc(status.label)}`));
    card.appendChild(head);
    const qr = item.query_range || {};
    const range = [qr.start_period, qr.end_period].filter(Boolean).join(" ~ ");
    if (range) card.appendChild(dsKv("区间", range));
    if (item.latest_report_period != null && item.latest_report_period !== "null") {
      card.appendChild(dsKv("最新期", item.latest_report_period));
    }
    card.appendChild(el(
      "p",
      "coverage-impact",
      status.cls === "off"
        ? `当前未获取到有效${type}，相关判断不会被补造，结论置信度会相应降低。`
        : `${type}已用于支持本次研究，仍需结合其他证据交叉判断。`,
    ));
    grid.appendChild(card);
  });
  return grid;
}

// Generic, bounded renderer for a content block's `data` — no fixed schema.
function renderBlockData(data) {
  const wrap = el("div", "op-note");
  wrap.textContent = "该部分暂无可安全展示的用户摘要。";
  return wrap;
}

// ---------------------------------------------------------------------------
// live: hall — real research submission (界面 01 · 实时)
// ---------------------------------------------------------------------------
const LIVE_RECOMMENDED = [
  "分析贵州茅台（600519.SH）近三个财年的盈利能力与财务质量",
  "评估宁德时代（300750.SZ）的成长性与估值水平",
  "全面分析比亚迪（002594.SZ）的基本面、行业竞争、宏观环境、量化表现与主要风险",
];

function pageHallLive() {
  const wrap = el("div");
  wrap.appendChild(screenTitle("01", "投研大厅", "描述研究问题，系统会拆解任务并编排合适的专家。"));

  const grid = el("div", "hall-grid");

  // ---- ask box ----
  const askPanel = el("div", "panel");
  const askTitle = el("div", "panel-title", "今天想研究什么？ <span class='title-extra'>提交后进入研究规划</span>");
  askPanel.appendChild(askTitle);
  const askBox = el("div", "ask-box");
  const ta = el("textarea");
  ta.placeholder = "例如：分析贵州茅台（600519.SH）近三个财年的盈利能力与财务质量…";
  if (liveSession.prompt) ta.value = liveSession.prompt;
  askBox.appendChild(ta);

  const refinement = el("div", "query-refinement");
  refinement.hidden = true;
  const queryActions = el("div", "query-actions");
  const originalToggle = el("button", "query-action", "查看原问题");
  originalToggle.type = "button";
  originalToggle.setAttribute("aria-expanded", "false");
  const retryRewrite = el("button", "query-action", "重新整理");
  retryRewrite.type = "button";
  queryActions.append(originalToggle, retryRewrite);
  const originalBox = el("div", "query-original");
  originalBox.hidden = true;
  const clarification = el("div", "query-clarification");
  clarification.hidden = true;
  const fallbackNote = el("div", "query-fallback-note");
  fallbackNote.hidden = true;
  refinement.append(queryActions, originalBox, clarification, fallbackNote);
  askBox.appendChild(refinement);

  const foot = el("div", "ask-foot");
  const count = el("span", "ask-count", `${ta.value.length} / 500`);
  const startBtn = el("button", "btn btn-primary", "🚀 开始研究");
  foot.append(count, startBtn);
  askBox.appendChild(foot);
  askPanel.appendChild(askBox);

  const rec = el("div", "rec-row");
  rec.appendChild(el("span", "rec-label", "常见研究"));
  LIVE_RECOMMENDED.forEach((t) => {
    const chip = el("button", "chip", esc(t));
    chip.addEventListener("click", () => { ta.value = t; count.textContent = `${ta.value.length} / 500`; ta.focus(); });
    rec.appendChild(chip);
  });
  askPanel.appendChild(rec);
  grid.appendChild(askPanel);

  let queryState = "input";
  let originalQuery = "";
  let rewrittenQuery = "";

  const updateCount = () => {
    count.textContent = `${ta.value.length} / 500`;
  };
  const setTitle = (title, hint) => {
    askTitle.innerHTML = `${esc(title)} <span class="title-extra">${esc(hint)}</span>`;
  };
  const showOriginal = (expanded) => {
    originalBox.hidden = !expanded;
    originalToggle.textContent = expanded ? "收起原问题" : "查看原问题";
    originalToggle.setAttribute("aria-expanded", expanded ? "true" : "false");
  };
  const renderClarification = (result) => {
    clarification.innerHTML = "";
    const options = result.needClarification ? result.options : [];
    clarification.hidden = !options.length;
    if (!options.length) return;
    clarification.appendChild(el("span", "query-clarification-label", "补充关键时间范围"));
    const optionRow = el("div", "query-option-row");
    options.forEach((option) => {
      const button = el("button", "query-option", esc(option));
      button.type = "button";
      button.addEventListener("click", () => {
        ta.value = applyClarificationOption(
          ta.value,
          option,
          result.clarificationType,
        );
        optionRow.querySelectorAll(".query-option").forEach((item) => {
          item.classList.toggle("sel", item === button);
        });
        updateCount();
        ta.focus();
      });
      optionRow.appendChild(button);
    });
    clarification.appendChild(optionRow);
  };
  const setOrganizingState = () => {
    queryState = "organizing";
    ta.readOnly = true;
    startBtn.disabled = true;
    startBtn.textContent = "正在整理研究问题…";
    retryRewrite.disabled = true;
    fallbackNote.hidden = true;
    rec.hidden = true;
  };
  const setConfirmationState = (result) => {
    queryState = "confirmation";
    rewrittenQuery = result.rewrittenQuery;
    ta.value = rewrittenQuery;
    ta.readOnly = false;
    refinement.hidden = false;
    retryRewrite.disabled = false;
    showOriginal(false);
    originalBox.textContent = originalQuery;
    renderClarification(result);
    fallbackNote.hidden = true;
    rec.hidden = true;
    setTitle("我理解你的研究需求是", "可直接修改");
    startBtn.disabled = false;
    startBtn.textContent = "确认并开始研究";
    updateCount();
    ta.focus();
  };
  const setFallbackState = () => {
    queryState = "fallback";
    rewrittenQuery = originalQuery;
    ta.value = originalQuery;
    ta.readOnly = false;
    refinement.hidden = false;
    retryRewrite.disabled = false;
    showOriginal(false);
    originalBox.textContent = originalQuery;
    clarification.hidden = true;
    fallbackNote.hidden = false;
    fallbackNote.textContent = "暂时无法自动整理，原问题已保留。你可以修改后直接继续。";
    rec.hidden = true;
    setTitle("研究问题整理暂时不可用", "可直接修改");
    startBtn.disabled = false;
    startBtn.textContent = "直接开始研究";
    updateCount();
    ta.focus();
  };
  const runRewrite = async ({ retry = false } = {}) => {
    const source = retry ? originalQuery : ta.value.trim();
    if (!source) {
      toast("请先描述你的研究意向");
      ta.focus();
      return;
    }
    if (!retry) originalQuery = source;
    setOrganizingState();
    try {
      const result = await liveRewriteResearchQuery(originalQuery);
      if (!result.requiresConfirmation) {
        const finalQuery = result.rewrittenQuery || originalQuery;
        beginLiveResearch(
          finalQuery,
          buildQueryContext(originalQuery, finalQuery, finalQuery),
        );
        return;
      }
      setConfirmationState(result);
    } catch {
      setFallbackState();
    }
  };
  const submit = () => {
    if (queryState === "organizing") return;
    if (queryState === "input") {
      runRewrite();
      return;
    }
    const finalQuery = ta.value.trim();
    if (!finalQuery) {
      toast("请保留一个可研究的问题");
      ta.focus();
      return;
    }
    startBtn.disabled = true;
    startBtn.textContent = "正在进入研究规划…";
    beginLiveResearch(
      finalQuery,
      buildQueryContext(originalQuery, rewrittenQuery, finalQuery),
    );
  };

  ta.addEventListener("input", updateCount);
  startBtn.addEventListener("click", submit);
  originalToggle.addEventListener("click", () => showOriginal(originalBox.hidden));
  retryRewrite.addEventListener("click", () => runRewrite({ retry: true }));

  // ---- live office preview ----
  const officePanel = el("div", "panel");
  officePanel.appendChild(el("div", "panel-title", "投研办公室 <span class='title-extra'>专家协作状态</span>"));
  const preview = el("div", "office-preview");
  const canvas = el("canvas");
  preview.appendChild(canvas);
  preview.appendChild(el("div", "live-tag", "<i></i>在线"));
  officePanel.appendChild(preview);
  const ofeed = el("div", "office-feed");
  ofeed.innerHTML = `<span class="dot"></span><span>正在读取在线专家…</span>`;
  officePanel.appendChild(ofeed);
  grid.appendChild(officePanel);
  wrap.appendChild(grid);

  // ---- online experts strip (async) ----
  const expertPanel = el("div", "panel");
  expertPanel.style.marginTop = "18px";
  const expertTitle = el("div", "panel-title", "在线专家 <span class='title-extra'>加载中…</span>");
  expertPanel.appendChild(expertTitle);
  const strip = el("div", "expert-strip");
  strip.appendChild(stateBox("loading", "正在读取专家…"));
  expertPanel.appendChild(strip);
  wrap.appendChild(expertPanel);

  // ---- overview stats (async) ----
  const statPanel = el("div", "panel");
  statPanel.style.marginTop = "18px";
  statPanel.appendChild(el("div", "panel-title", "系统概览"));
  const cards = el("div", "stat-cards");
  statPanel.appendChild(cards);
  wrap.appendChild(statPanel);

  Promise.all([fetchExperts(), fetchOverview()])
    .then(([experts, ov]) => {
      const online = experts.filter((e) => e.status !== "off");
      // office scene can only draw agents that have a pixel sprite sheet
      const scene = experts.filter((e) => SPRITE_MAP[e.id]);
      requestAnimationFrame(() => drawOfficeScene(canvas, scene));
      const ofeedSpan = ofeed.querySelector("span:last-child");
      if (ofeedSpan) ofeedSpan.textContent = `${online.length} 位专家在线协作`;
      expertTitle.innerHTML = `在线专家 <span class='title-extra'>${online.length} 位专家在线协作</span>`;
      strip.innerHTML = "";
      experts.forEach((a) => {
        const card = el("button", "expert-mini");
        card.appendChild(avatar(a.id, 56, "em-ava"));
        card.appendChild(el("strong", "", esc(a.name)));
        card.appendChild(el("div", "em-role", esc(a.role)));
        card.appendChild(el("span", `badge ${a.status}`, `<span class="dot"></span>${statusText(a.status)}`));
        card.appendChild(el("div", "em-spec", esc(a.specialty)));
        card.addEventListener("click", () => navigate("experts"));
        strip.appendChild(card);
      });
      cards.innerHTML = "";
      [
        { num: `${ov.enabled_experts}`, label: "在线专家", sub: "当前可调度", green: true, route: "experts" },
        { num: `${ov.enabled_skills}`, label: "可用研究能力", sub: "专业分析方法", route: "skills" },
        { num: `${ov.total_tasks}`, label: "累计任务", sub: `含 ${ov.completed_tasks} 个已完成`, route: "tasks" },
        { num: `${ov.report_count}`, label: "已生成报告", sub: "可追问 / 检索", route: "reports" },
      ].forEach((s) => {
        const c = el("button", "stat-card");
        c.innerHTML = `<div class="sc-num${s.green ? " green" : ""}">${esc(s.num)}</div><div class="sc-label">${esc(s.label)}</div><div class="sc-sub">${esc(s.sub)}</div>`;
        c.addEventListener("click", () => navigate(s.route));
        cards.appendChild(c);
      });
    })
    .catch((err) => {
      strip.innerHTML = "";
      strip.appendChild(stateBox("error", "无法读取在线专家", "当前无法更新专家状态，请稍后重试。"));
      requestAnimationFrame(() => drawOfficeScene(canvas, []));
    });

  return wrap;
}

// ---------------------------------------------------------------------------
// live: clarify — render real Manager clarification groups
// ---------------------------------------------------------------------------
function pageClarifyLive() {
  const session = liveSession;
  if (!session.taskId || !session.plan) {
    const wrap = el("div", "panel");
    wrap.appendChild(screenTitle("02", "任务澄清", ""));
    const box = stateBox("empty", "尚无进行中的规划会话", "请先在投研大厅提交研究请求。");
    const back = el("button", "btn btn-primary", "‹ 返回大厅");
    back.style.marginTop = "10px";
    back.addEventListener("click", () => navigate("hall"));
    box.appendChild(back);
    wrap.appendChild(box);
    return wrap;
  }

  const plan = session.plan;
  const groups = plan.clarificationOptions || [];
  const sel = {};
  groups.forEach((g) => {
    sel[g.key] = new Set();
    if (g.def != null && g.items.includes(g.def)) sel[g.key].add(g.items.indexOf(g.def));
  });

  const layout = el("div", "chat-layout");

  // ---- left: Manager conversation ----
  const left = el("div", "panel chat-col");
  left.appendChild(screenTitle("02", "任务澄清", "请先确认关键口径，系统会据此安排后续研究。"));

  const head = el("div", "chat-head");
  head.appendChild(avatar("manager", 46, "pix-ava"));
  const who = el("div", "who");
  who.innerHTML = "<strong>研究经理</strong><small>正在澄清任务需求…</small>";
  head.appendChild(who);
  left.appendChild(head);

  const scroll = el("div", "chat-scroll");
  scroll.appendChild(clarifyMsg("bot", esc(plan.clarificationQuestion || "在正式开工前，请确认以下关键研究口径。")));

  if (groups.length) {
    const gridMsg = el("div", "msg");
    const gAva = el("div", "m-avatar");
    gAva.appendChild(avatar("manager", 38));
    const gBody = el("div", "m-body");
    gBody.style.maxWidth = "none";
    gBody.appendChild(el("div", "m-meta", "<span>研究经理</span><span>关键澄清项</span>"));
    const gridWrap = el("div", "m-bubble");
    gridWrap.style.width = "100%";
    const optGrid = el("div", "clarify-grid");
    gridWrap.appendChild(optGrid);
    gBody.appendChild(gridWrap);
    gridMsg.append(gAva, gBody);
    scroll.appendChild(gridMsg);

    const renderGrid = () => {
      optGrid.innerHTML = "";
      groups.forEach((g) => {
        const card = el("div", "opt-card");
        card.appendChild(el("h5", "", `${esc(g.title)} <small>${g.multi ? "可多选" : "单选"}</small>`));
        if (g.hint) card.appendChild(el("div", "op-note", esc(g.hint)));
        const list = el("div", "opt-list");
        g.items.forEach((label, i) => {
          const on = sel[g.key].has(i);
          const item = el("button", `opt-item${on ? " sel" : ""}`);
          item.innerHTML = `<span>${esc(label)}</span>${on ? '<span class="tick">✓</span>' : ""}`;
          item.addEventListener("click", () => {
            if (g.multi) {
              if (sel[g.key].has(i)) sel[g.key].delete(i); else sel[g.key].add(i);
            } else {
              sel[g.key].clear(); sel[g.key].add(i);
            }
            renderGrid();
          });
          list.appendChild(item);
        });
        card.appendChild(list);
        optGrid.appendChild(card);
      });
    };
    renderGrid();
  }

  scroll.appendChild(clarifyMsg("bot", "确认后点击右侧「确认并提交澄清」，系统会据此重新规划并开始研究。"));
  left.appendChild(scroll);

  const inputBar = el("div", "chat-inputbar");
  const input = el("input");
  input.type = "text";
  input.placeholder = "补充说明（可选）：例如特别关注的时间段或指标…";
  inputBar.appendChild(input);
  left.appendChild(inputBar);

  // ---- right: confirm panel ----
  const right = el("div", "panel chat-col");
  right.appendChild(el("div", "panel-title", "澄清摘要"));
  const kv = el("div", "summary-kv");
  kv.appendChild(el("div", "", `<div class="k">研究目标</div><div>${esc(plan.goal || session.prompt)}</div>`));
  if (plan.intent) kv.appendChild(el("div", "", `<div class="k">识别意图</div><div>${esc(plan.intent)}</div>`));
  if (plan.complexity) kv.appendChild(el("div", "", `<div class="k">复杂度</div><div>${esc(plan.complexity)}</div>`));
  right.appendChild(kv);

  const go = el("button", "btn btn-primary", "🚀 确认并提交澄清");
  go.style.cssText = "width:100%;margin-top:16px";
  go.addEventListener("click", () => {
    const answers = {};
    groups.forEach((g) => {
      const chosen = [...sel[g.key]].sort((a, b) => a - b).map((i) => g.items[i]);
      if (!chosen.length) return;
      answers[g.key] = g.multi ? chosen : chosen[0];
    });
    const supplement = input.value.trim();
    if (supplement) answers.supplement = supplement;
    go.disabled = true;
    go.textContent = "正在重新规划…";
    liveClarifySession(session.taskId, answers)
      .then(({ taskId, plan: nextPlan }) => {
        setLiveSession({ taskId, plan: nextPlan });
        navigate(nextPlan && nextPlan.needsClarification ? "clarify" : "war");
      })
      .catch((err) => {
        go.disabled = false;
        go.textContent = "🚀 确认并提交澄清";
        toast("澄清提交未完成：研究服务暂时不可用，请稍后重试。");
      });
  });
  right.appendChild(go);

  const edit = el("button", "btn-ghost", "‹ 返回大厅重新描述");
  edit.style.cssText = "width:100%;margin-top:8px";
  edit.addEventListener("click", () => navigate("hall"));
  right.appendChild(edit);

  layout.append(left, right);
  return layout;
}

// ---------------------------------------------------------------------------
// live: war room — consume real SSE execution stream (界面 03 · 实时)
// ---------------------------------------------------------------------------
function pageManagerPlanningLive(session) {
  const state = session.researchState;
  const fixedStockWorkflow = state?.workflowMode === "stock_analysis";
  const stageLabels = {
    received: "请求已接收",
    interpreting: fixedStockWorkflow ? "正在校验股票信息" : "正在理解用户目标",
    interpreted: fixedStockWorkflow ? "固定研究范围已确认" : "目标解释完成",
    selecting_agents: fixedStockWorkflow ? "正在装配固定专家组" : "正在动态选择专家",
    agents_selected: fixedStockWorkflow ? "固定专家组已就绪" : "专家选择完成",
    building_dag: fixedStockWorkflow ? "正在生成固定任务图" : "正在生成依赖 DAG",
    validating_dag: fixedStockWorkflow ? "正在校验固定任务图" : "正在校验依赖 DAG",
    plan_ready: "研究计划已就绪",
  };
  const stageOrder = [
    "received",
    "interpreting",
    "interpreted",
    "selecting_agents",
    "agents_selected",
    "building_dag",
    "validating_dag",
    "plan_ready",
  ];
  const stageRank = state ? stageOrder.indexOf(state.currentStage) : -1;
  const progress = state ? Math.max(0, Math.min(100, state.progress)) : null;
  const elapsedSeconds = state ? Math.max(0, Math.floor(state.elapsedMs / 1000)) : 0;
  const timingText = state && state.estimatedRemainingMs != null
    ? `基于历史真实耗时，预计还需约 ${Math.max(1, Math.ceil(state.estimatedRemainingMs / 1000))} 秒`
    : state
      ? `已等待 ${elapsedSeconds} 秒`
      : "正在连接后端运行状态";
  const selectedAgents = state?.selectedAgents || [];

  const wrap = el("div", "war-room-page war-room-page-planning");
  const head = el("div", "war-head");
  head.appendChild(el("h1", "", "研究作战室"));
  head.appendChild(el(
    "span",
    "sub",
    fixedStockWorkflow ? "固定 Agent 工作流 · 效率优先" : "后端真实规划状态",
  ));
  const task = el("div", "war-task");
  task.appendChild(el("span", "wt-name", esc(session.prompt)));
  task.appendChild(el(
    "span",
    "badge running",
    `<span class="dot"></span>${esc(state ? stageLabels[state.currentStage] || "规划中" : "连接中")}`,
  ));
  head.appendChild(task);
  wrap.appendChild(head);

  const panel = el("div", "panel manager-planning-shell");
  panel.appendChild(el(
    "div",
    "panel-title",
    `任务拆解 <span class='title-extra'>${esc(state?.message || "等待后端状态")}</span>`,
  ));

  const progressRow = el("div", "manager-planning-progress");
  progressRow.innerHTML = `
    <span>${progress == null ? "—" : `${progress}%`}</span>
    <div class="pbar"><i style="width:${progress == null ? 0 : progress}%"></i></div>
    <small>${esc(timingText)}</small>
  `;
  panel.appendChild(progressRow);

  const flow = el("div", "manager-planning-flow");
  const manager = el("div", "manager-core is-planning");
  manager.innerHTML = `
    <span class="manager-core-icon">${fixedStockWorkflow ? "⚡" : "🧠"}</span>
    <strong>${fixedStockWorkflow ? "固定研究编排器" : "研究经理"}</strong>
    <small>${esc(state?.message || "等待后端开始解释研究目标")}</small>
    <span class="badge running"><span class="dot"></span>${esc(state ? stageLabels[state.currentStage] || "研究规划进行中" : "正在连接")}</span>
  `;
  flow.appendChild(manager);

  const arrow = el("div", "manager-arrow", "→");
  arrow.setAttribute("aria-hidden", "true");
  flow.appendChild(arrow);

  const pending = el("div", "manager-pending");
  pending.appendChild(el(
    "strong",
    "",
    selectedAgents.length
      ? fixedStockWorkflow ? "固定专家组" : "本次动态专家"
      : fixedStockWorkflow ? "固定专家预设" : "动态专家池",
  ));
  if (selectedAgents.length) {
    const list = el("div", "manager-selected-list");
    selectedAgents.forEach((selection) => {
      const info = researchPresentation
        ? researchPresentation.agentInfo(selection.agent)
        : { name: selection.agent };
      const item = el("div", "manager-selected-item");
      item.innerHTML = `
        <span>${esc(info.name || selection.agent)}</span>
        <small>${esc(selection.reason || (fixedStockWorkflow ? "由股票分析预设固定加入" : "由研究经理按任务需要选择"))}</small>
      `;
      list.appendChild(item);
    });
    pending.appendChild(list);
    pending.appendChild(el(
      "small",
      "",
      fixedStockWorkflow ? "以上专家来自股票分析固定预设" : "以上结果来自研究经理的真实返回",
    ));
  } else {
    pending.appendChild(el("span", "", "尚未返回选择结果"));
    pending.appendChild(el(
      "small",
      "",
      fixedStockWorkflow ? "正在校验固定专家是否可用" : "研究经理完成选择前不会预设任何专家",
    ));
  }
  flow.appendChild(pending);
  panel.appendChild(flow);

  const stages = el("div", "manager-planning-stages");
  [
    ["01", fixedStockWorkflow ? "校验股票与研究范围" : "理解用户目标", 1, 2],
    ["02", fixedStockWorkflow ? "装配固定专家组" : "选择最小充分专家集合", 3, 4],
    ["03", fixedStockWorkflow ? "生成并验证固定 DAG" : "生成并验证依赖 DAG", 5, 7],
  ].forEach(([num, label, startRank, endRank]) => {
    const visualState = stageRank >= endRank
      ? "is-done"
      : stageRank >= startRank
        ? "is-active"
        : "is-pending";
    const stage = el("div", `manager-planning-stage ${visualState}`);
    stage.innerHTML = `<span>${num}</span><strong>${esc(label)}</strong><em>${visualState === "is-done" ? "已完成" : visualState === "is-active" ? "进行中" : "等待"}</em>`;
    stages.appendChild(stage);
  });
  panel.appendChild(stages);
  panel.appendChild(el(
    "p",
    "manager-truth-note",
    session.connectionIssue
      ? "实时连接暂时中断，正在自动重连，并通过状态接口恢复。"
      : "进度、阶段、专家和 DAG 均由后端真实执行状态提供。",
  ));
  wrap.appendChild(panel);
  return wrap;
}

function pageWarRoomLive() {
  const session = liveSession;
  if (!session.taskId) {
    if (session.phase === "planning" && session.prompt) {
      return pageManagerPlanningLive(session);
    }
    const wrap = el("div", "panel war-room-page");
    wrap.appendChild(el("div", "panel-title", "研究作战室"));
    const failed = session.phase === "failed";
    const fixedWorkflow = (
      session.researchState?.workflowMode === "stock_analysis"
      || session.workflowMode === "stock_analysis"
    );
    const box = stateBox(
      failed ? "error" : "empty",
      failed
        ? fixedWorkflow ? "固定工作流启动失败" : "Manager 规划失败"
        : "尚无进行中的任务",
      failed
        ? `${session.researchState?.failedStage ? `失败阶段：${session.researchState.failedStage}。` : ""}${session.error || "研究服务未能完成任务规划。"}`
        : "请先在投研大厅提交研究请求。",
    );
    if (failed && session.prompt) {
      const retry = el("button", "btn btn-primary", "重新尝试");
      retry.style.marginTop = "10px";
      retry.addEventListener("click", () => beginLiveResearch(
        session.prompt,
        {
          ...buildQueryContext(
            session.originalQuery,
            session.rewrittenQuery,
            session.finalQuery || session.prompt,
          ),
          workflowMode: session.workflowMode || "dynamic",
          stockSymbol: session.stockSymbol || "",
          stockName: session.stockName || "",
          stockBoard: session.stockBoard || "",
        },
      ));
      box.appendChild(retry);
    }
    const back = el("button", "btn btn-primary", "‹ 返回大厅");
    back.style.marginTop = "10px";
    back.addEventListener("click", () => navigate("hall"));
    box.appendChild(back);
    wrap.appendChild(box);
    return wrap;
  }

  const plan = session.plan;
  const steps = (plan && plan.steps) || [];
  const wrap = el("div", "war-room-page");

  // ---- head ----
  const head = el("div", "war-head");
  head.appendChild(el("h1", "", "研究作战室"));
  head.appendChild(el("span", "sub", "研究进度与专家协作"));
  const task = el("div", "war-task");
  task.appendChild(el("span", "wt-name", esc(plan && plan.goal ? plan.goal : session.prompt)));
  const badge = el("span", "badge running", '<span class="dot"></span>执行中');
  task.appendChild(badge);
  const reportBtn = el("button", "btn btn-primary war-report-btn", "查看报告 →");
  reportBtn.style.display = "none";
  task.appendChild(reportBtn);
  head.appendChild(task);
  wrap.appendChild(head);

  // Manager is a coordinator, not a DAG step. This strip visualizes the
  // Manager's real selections separately from the expert execution graph.
  const managerFlow = el("div", "panel manager-dispatch");
  const managerCard = el("div", "manager-dispatch-card");
  managerCard.innerHTML = `
    <span class="manager-core-icon">🧠</span>
    <span><strong>研究经理</strong><small>动态选人与任务编排</small></span>
    <span class="badge done manager-dispatch-status"><span class="dot"></span>计划已验证</span>
  `;
  managerFlow.appendChild(managerCard);
  managerFlow.appendChild(el("div", "manager-dispatch-arrow", "研究分工"));
  const managerAgents = el("div", "manager-agent-list");
  const agentFlowEls = {};
  ((plan && plan.agents) || []).forEach((agent) => {
    const publicAgent = researchPresentation
      ? researchPresentation.agentInfo(agent.id)
      : { name: agent.role || "AI 投研专家", role: agent.role || "" };
    const chip = el("div", "manager-agent-chip idle");
    chip.title = agent.reason || "";
    chip.innerHTML = `
      <span class="manager-agent-avatar">${esc(publicAgent.name.slice(0, 1))}</span>
      <span><strong>${esc(publicAgent.name)}</strong><small>${esc(publicAgent.role)}</small></span>
      <em>已入列</em>
    `;
    agentFlowEls[agent.id] = chip;
    managerAgents.appendChild(chip);
  });
  managerFlow.appendChild(managerAgents);
  wrap.appendChild(managerFlow);

  const grid = el("div", "war-grid");

  // ---- LEFT: real DAG built from plan.steps (layered by dependency depth) ----
  const leftCol = el("div", "panel war-left-col");
  leftCol.appendChild(el("div", "panel-title", "任务执行流"));
  const dag = el("div", "dag-wrap dag-stack");
  const byId = {};
  steps.forEach((s) => { byId[s.id] = s; });
  const depth = {};
  const computeDepth = (id, seen) => {
    if (depth[id] != null) return depth[id];
    const s = byId[id];
    if (!s || !s.dependsOn.length || seen.has(id)) { depth[id] = 0; return 0; }
    seen.add(id);
    depth[id] = 1 + Math.max(...s.dependsOn.map((p) => computeDepth(p, seen)));
    return depth[id];
  };
  steps.forEach((s) => computeDepth(s.id, new Set()));
  const layers = {};
  steps.forEach((s) => { (layers[depth[s.id]] = layers[depth[s.id]] || []).push(s); });
  const layerKeys = Object.keys(layers).map(Number).sort((a, b) => a - b);
  const edgeEls = {};
  const nodeEls = {};
  layerKeys.forEach((d, layerIndex) => {
    if (layerIndex > 0) dag.appendChild(el("div", "dag-layer-join", "↓"));
    const layer = el("div", `dag-layer${layers[d].length === 1 ? " single" : " multi"}`);
    layer.style.setProperty("--dag-cols", String(layers[d].length));
    layers[d].forEach((s) => {
      const node = el("button", "dag-node st-idle");
      node.appendChild(avatar(s.agent, 34, "dn-ava"));
      const publicAgent = researchPresentation
        ? researchPresentation.agentInfo(s.agent)
        : { name: s.role || "AI 投研专家", role: s.role || "" };
      node.appendChild(el("strong", "", esc(publicAgent.name)));
      node.appendChild(el("small", "", esc(s.objective || publicAgent.role)));
      if (s.dependsOn.length) {
        node.appendChild(el(
          "span",
          "dag-deps",
          `依赖 ${esc(s.dependsOn.map((id) => byId[id]?.agent || id).join(" / "))}`,
        ));
      }
      node.appendChild(el("span", "badge off dn-badge", '<span class="dot"></span>待命'));
      node.title = s.objective || "";
      node.addEventListener("click", () => navigate("experts"));
      nodeEls[s.id] = node;
      layer.appendChild(node);
    });
    dag.appendChild(layer);
  });
  if (!steps.length) dag.appendChild(stateBox("empty", "该计划无可执行步骤"));
  leftCol.appendChild(dag);
  grid.appendChild(leftCol);

  // ---- CENTER: live stage + progress ----
  const centerCol = el("div", "war-center-col");
  const stagePanel = el("div", "panel");
  stagePanel.appendChild(el("div", "panel-title", "专家协作 <span class='title-extra'>研究执行中</span>"));
  const stage = el("div", "office-stage");
  const canvas = el("canvas");
  stage.appendChild(canvas);
  stagePanel.appendChild(stage);

  const prog = el("div", "progress-row");
  const pmain = el("div");
  pmain.innerHTML = '<div style="font-size:12px;color:var(--text-2);margin-bottom:6px">整体进度 <b class="p-pct" style="color:var(--cyan)">0%</b></div><div class="pbar"><i style="width:0%"></i></div>';
  prog.appendChild(pmain);
  const pstats = {
    done: el("div", "pstat", '<strong>0</strong><span>已完成</span>'),
    working: el("div", "pstat", '<strong>0</strong><span>进行中</span>'),
    logs: el("div", "pstat", '<strong>0</strong><span>日志</span>'),
    elapsed: el("div", "pstat", '<strong>0s</strong><span>用时</span>'),
  };
  prog.append(pstats.done, pstats.working, pstats.logs, pstats.elapsed);
  stagePanel.appendChild(prog);
  centerCol.appendChild(stagePanel);

  // companion interpretation feed（挂到右栏，保持中栏单屏）
  const companionPanel = el("div", "panel companion-panel");
  companionPanel.style.marginTop = "0";
  companionPanel.appendChild(el("div", "panel-title", "🔍 专家解读"));
  const companionFeed = el("div", "companion-feed");
  companionPanel.appendChild(companionFeed);

  // coach classroom feed: model-generated narrations arrive over SSE, and
  // earlier narrations for this task are replayed from the read-only API.
  const classroom = createClassroomPanel({
    agentName: (id) => (researchPresentation
      ? researchPresentation.agentInfo(id).name
      : id),
  });
  fetchCoachNarrations(session.taskId)
    .then((rows) => (rows || []).forEach((n) => classroom.push(n)))
    .catch(() => { /* replay is best-effort; live SSE still feeds the panel */ });

  grid.appendChild(centerCol);

  // ---- RIGHT: interpretation + classroom + logs（研究方法挪到左栏 DAG 下方）----
  const rightCol = el("div", "war-right-col");
  const skillPanel = el("div", "panel");
  skillPanel.style.marginTop = "14px";
  skillPanel.appendChild(el("div", "panel-title", "专业研究方法"));
  const skillList = el("div", "skill-list");
  skillPanel.appendChild(skillList);
  const skillEmpty = el("div", "op-note", "专家尚未开始专业分析步骤");
  skillPanel.appendChild(skillEmpty);
  leftCol.appendChild(skillPanel);

  rightCol.appendChild(companionPanel);
  rightCol.appendChild(classroom.root);

  const logPanel = el("div", "panel");
  logPanel.style.marginTop = "14px";
  logPanel.appendChild(el("div", "panel-title", "研究日志"));
  const logEl = el("div", "log-list");
  logPanel.appendChild(logEl);
  rightCol.appendChild(logPanel);
  grid.appendChild(rightCol);

  wrap.appendChild(grid);

  // office scene from plan agents (only those with a pixel sprite sheet)
  const planAgents = (plan && plan.agents && plan.agents.length)
    ? plan.agents.filter((a) => SPRITE_MAP[a.id]).map((a) => {
        const publicAgent = researchPresentation
          ? researchPresentation.agentInfo(a.id)
          : { name: a.name || a.id };
        return { id: a.id, name: publicAgent.name || a.name || a.id, status: "idle" };
      })
    : [];
  const stageController = createOfficeStageController(canvas, planAgents);

  // ---- engine state ----
  const startedAt = Date.now();
  const skillCounts = {};
  const stepStatus = {};
  let logCount = 0;
  let reportId = null;
  let completionStatus = null;

  const elapsedTimer = setInterval(() => {
    pstats.elapsed.querySelector("strong").textContent = `${Math.floor((Date.now() - startedAt) / 1000)}s`;
  }, 1000);

  const DAG_LABEL = { running: "执行中", done: "已完成", failed: "失败" };
  const setAgentFlow = (agentId) => {
    const chip = agentFlowEls[agentId];
    if (!chip) return;
    const statuses = steps
      .filter((step) => step.agent === agentId)
      .map((step) => stepStatus[step.id])
      .filter(Boolean);
    let state = "idle";
    let label = "已入列";
    if (statuses.some((status) => status === "running")) {
      state = "running";
      label = "执行中";
    } else if (statuses.some((status) => status === "failed")) {
      state = "failed";
      label = "执行失败";
    } else if (
      statuses.length > 0
      && steps.filter((step) => step.agent === agentId).every((step) => stepStatus[step.id] === "done")
    ) {
      state = "done";
      label = "已完成";
    } else if (statuses.some((status) => status === "done")) {
      state = "waiting";
      label = "等待后续";
    }
    chip.className = `manager-agent-chip ${state}`;
    const statusEl = chip.querySelector("em");
    if (statusEl) statusEl.textContent = label;
  };
  const setNode = (stepId, status) => {
    const node = nodeEls[stepId];
    if (!node) return;
    const cls = status === "done" ? "st-done" : status === "failed" ? "st-off" : "st-running";
    node.className = `dag-node ${cls}`;
    const b = node.querySelector(".dn-badge");
    if (b) {
      const bcls = status === "done" ? "done" : status === "failed" ? "off" : "running";
      b.className = `badge ${bcls} dn-badge`;
      b.innerHTML = `<span class="dot"></span>${DAG_LABEL[status] || status}`;
    }
    Object.entries(edgeEls).forEach(([key, ln]) => {
      if (key.startsWith(`${stepId}-`) && (status === "running" || status === "done")) {
        ln.setAttribute("stroke", "#111111");
        ln.setAttribute("stroke-width", "0.8");
      }
    });
  };

  const updateProgress = () => {
    const total = steps.length || 1;
    const done = Object.values(stepStatus).filter((v) => v === "done" || v === "failed").length;
    const working = Object.values(stepStatus).filter((v) => v === "running").length;
    const pct = Math.round((done / total) * 100);
    pmain.querySelector(".p-pct").textContent = `${pct}%`;
    pmain.querySelector(".pbar i").style.width = `${pct}%`;
    pstats.done.querySelector("strong").textContent = String(done);
    pstats.working.querySelector("strong").textContent = String(working);
  };

  const LOG_COLOR = { done: "var(--green)", fail: "var(--red)", run: "var(--blue)", skill: "var(--cyan)", tool: "var(--yellow)" };
  const pushLog = (who, message, kind) => {
    logCount++;
    pstats.logs.querySelector("strong").textContent = String(logCount);
    const line = el("div", "log-line");
    line.innerHTML = `<span class="lt">${esc(nowClock())}</span><span class="la" style="color:${LOG_COLOR[kind] || "var(--text-2)"}">${esc(who || "system")}</span><span>${esc(message || "")}</span>`;
    logEl.appendChild(line);
    while (logEl.children.length > 60) logEl.removeChild(logEl.firstChild);
    logEl.scrollTop = logEl.scrollHeight;
  };

  const bumpSkill = (agentId) => {
    if (!agentId) return;
    const publicAgent = researchPresentation
      ? researchPresentation.agentInfo(agentId)
      : { name: "AI 投研专家" };
    const name = `${publicAgent.name} · 专业分析`;
    skillCounts[name] = (skillCounts[name] || 0) + 1;
    skillEmpty.style.display = "none";
    let row = skillList.querySelector(`[data-skill="${window.CSS && CSS.escape ? CSS.escape(name) : name}"]`);
    if (!row) {
      row = el("div", "skill-row");
      row.setAttribute("data-skill", name);
      row.innerHTML = `<span></span><span>${esc(name)}</span><span class="sk-count">0</span>`;
      skillList.appendChild(row);
    }
    row.querySelector(".sk-count").textContent = String(skillCounts[name]);
  };

  const handleEvent = (evt) => {
    const agent = evt.agent || "";
    const stepId = evt.step_id;
    const publicAgent = researchPresentation
      ? researchPresentation.agentInfo(agent).name
      : "研究团队";
    const publicMessage = researchPresentation
      ? researchPresentation.translateProgressEvent({
          ...evt,
          objective: steps.find((step) => step.id === stepId)?.objective || "",
        })
      : "研究团队正在更新任务进度。";
    switch (evt.type) {
      case "plan_created":
        managerCard.querySelector(".manager-dispatch-status").innerHTML = '<span class="dot"></span>分派完成';
        pushLog("研究经理", publicMessage);
        break;
      case "step_started":
        if (stepId) { stepStatus[stepId] = "running"; setNode(stepId, "running"); }
        if (agent) setAgentFlow(agent);
        if (agent) stageController.setAgentStatus(agent, "working");
        pushLog(publicAgent, publicMessage, "run");
        break;
      case "step_completed":
        if (stepId) { stepStatus[stepId] = "done"; setNode(stepId, "done"); }
        if (agent) setAgentFlow(agent);
        if (agent) stageController.setAgentStatus(agent, "done");
        pushLog(publicAgent, publicMessage, "done");
        (() => {
          try {
            const cd = companionAdapter(agent, evt.metadata || {});
            if (cd) renderCompanionCard(companionFeed, cd);
          } catch (e) { /* silently skip malformed companion data */ }
        })();
        break;
      case "step_failed":
        if (stepId) { stepStatus[stepId] = "failed"; setNode(stepId, "failed"); }
        if (agent) setAgentFlow(agent);
        if (agent) stageController.setAgentStatus(agent, "failed");
        pushLog(publicAgent, publicMessage, "fail");
        break;
      case "skill_plan_created":
        pushLog(publicAgent, publicMessage, "skill");
        break;
      case "skill_started":
        bumpSkill(agent);
        pushLog(publicAgent, publicMessage, "skill");
        break;
      case "skill_completed":
        pushLog(publicAgent, publicMessage, "skill");
        break;
      case "skill_failed":
        pushLog(publicAgent, publicMessage, "fail");
        break;
      case "tool_called":
        pushLog(publicAgent, publicMessage, "tool");
        break;
      case "synthesis_started":
        pushLog("研究整合专家", publicMessage, "run");
        break;
      case "task_completed":
        planAgents.forEach((a) => stageController.setAgentStatus(a.id, "idle"));
        pushLog("研究团队", publicMessage, "done");
        break;
      default:
        pushLog(publicAgent, publicMessage);
    }
    updateProgress();
  };

  const src = openTaskStream(session.taskId, {
    onEvent: handleEvent,
    onCoach: (n) => classroom.push(n),
    onAggregation: (data) => {
      if (data && data.report_id) reportId = data.report_id;
      completionStatus = data && data.aggregation
        ? data.aggregation.completion_status
        : completionStatus;
      const succeeded = completionStatus === "completed";
      const partial = completionStatus === "partially_completed";
      pushLog(
        "report",
        succeeded
          ? "聚合报告已成功生成"
          : partial
            ? "聚合报告已部分生成"
            : "聚合未能形成有效报告，已保存失败说明",
        succeeded || partial ? "done" : "fail",
      );
    },
    onDone: (data) => {
      clearInterval(elapsedTimer);
      classroom.finish();
      completionStatus = (data && data.status) || completionStatus || "failed";
      const succeeded = completionStatus === "completed";
      const partial = completionStatus === "partially_completed";
      badge.className = succeeded ? "badge online" : "badge busy";
      badge.innerHTML = `<span class="dot"></span>${succeeded ? "已完成" : partial ? "部分完成" : "执行失败"}`;
      updateProgress();
      const finalReport = reportId || (data && data.report_id) || null;
      pushLog(
        "system",
        succeeded || partial
          ? "任务结束，可查看完整报告"
          : "任务失败，可查看失败说明",
        succeeded || partial ? "done" : "fail",
      );
      if (finalReport) {
        rememberCurrentReport(finalReport);
        setLiveSession({ phase: "completed" });
        navigate("reports", finalReport);
        return;
      }
      reportBtn.style.display = "";
      reportBtn.textContent = "查看历史记录 →";
      reportBtn.addEventListener("click", () => navigate("tasks"), { once: true });
    },
    onError: (info) => {
      clearInterval(elapsedTimer);
      badge.className = "badge busy";
      badge.innerHTML = '<span class="dot"></span>执行失败';
      pushLog("system", (info && info.detail) || "任务执行失败", "fail");
    },
  });

  registerTeardown(() => {
    clearInterval(elapsedTimer);
    stageController.stop();
    try { src.close(); } catch (_) {}
  });

  return wrap;
}

// ---------------------------------------------------------------------------
// boot
// ---------------------------------------------------------------------------
function boot() {
  initOfficeGlossary();
  renderTopbar();
  renderStatusbar();
  renderSidebar();
  // expose the router so hall hero / LIVE-office previews can jump into the
  // clarify + war-room sub-flows (which have no top-level nav entry).
  window.__navigate = navigate;
  window.__openProfileOnboarding = () => openProfileOnboarding(toast);
  if (isLive()) {
    // Live mode probes the backend before opening the stock library.
    refreshServiceStatus().finally(() => {
      renderTopbar();
      navigate("stock-library");
    });
  } else {
    // Demo mode starts from the same separated stock-library entry point.
    navigate("stock-library");
  }
  maybeStartProfileOnboarding(toast);
  setInterval(renderStatusbar, 30_000);
}

boot();
