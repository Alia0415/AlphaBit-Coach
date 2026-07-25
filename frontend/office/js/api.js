// AlphaBit Coach backend API client. Demo mode reads mock.js instead of this file.

// Manager planning may include model retries and can legitimately exceed the
// generic request timeout. Keep the browser waiting while the backend owns the
// authoritative task state instead of showing a false failure at 90 seconds.
const PLANNING_TIMEOUT_MS = 300000;

// Same-origin by default (FastAPI serves the office at /office). A different
// backend origin can be pinned via localStorage for standalone hosting.
function apiBase() {
  try {
    return (localStorage.getItem("alphaos.apiBase") || "").replace(/\/$/, "");
  } catch {
    return "";
  }
}

async function requestJSON(
  path,
  { method = "GET", body, timeoutMs = 8000 } = {},
) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(apiBase() + path, {
      method,
      headers: {
        Accept: "application/json",
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: ctrl.signal,
    });
    if (!res.ok) {
      let message = "请求失败，请稍后重试。";
      try {
        const payload = await res.json();
        if (typeof payload.detail === "string") message = payload.detail;
        else if (Array.isArray(payload.detail) && payload.detail[0]?.msg) {
          message = payload.detail[0].msg.replace(/^Value error, /, "");
        }
      } catch {
        // Keep the plain-language fallback.
      }
      throw new Error(message);
    }
    if (res.status === 204) return null;
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

const getJSON = (path, options = {}) => requestJSON(path, options);
const postJSON = (path, body, options = {}) =>
  requestJSON(path, { ...options, method: "POST", body });

export const api = {
  // service status
  health: () => getJSON("/api/health", { timeoutMs: 4000 }),
  pandadataStatus: () => getJSON("/api/pandadata/status", { timeoutMs: 4000 }),

  // read-only surfaces
  overview: () => getJSON("/api/overview"),
  experts: () => getJSON("/api/experts"),
  skills: () => getJSON("/api/skills"),
  tasks: () => getJSON("/api/tasks"),
  task: (id) => getJSON(`/api/tasks/${encodeURIComponent(id)}`),
  reports: () => getJSON("/api/reports"),
  report: (id) => getJSON(`/api/reports/${encodeURIComponent(id)}`),
  reportGlossary: (id) =>
    postJSON(`/api/reports/${encodeURIComponent(id)}/glossary`, undefined, {
      timeoutMs: 90000,
    }),

  // task and read-only-surface actions
  plan: (prompt) =>
    requestJSON("/api/plan", { method: "POST", body: { prompt } }),
  runTask: (prompt) =>
    requestJSON("/api/tasks", { method: "POST", body: { prompt } }),
  setExpertEnabled: (id, enabled) =>
    postJSON(`/api/experts/${encodeURIComponent(id)}/enabled`, { enabled }),
  reportFollowup: (id, question) =>
    postJSON(`/api/reports/${encodeURIComponent(id)}/followup`, { question }),

  // AI coach layer (model-backed; generous timeouts for model calls)
  coachAsk: (id, question, quotedText) =>
    postJSON(
      `/api/reports/${encodeURIComponent(id)}/coach`,
      { question, quoted_text: quotedText || null },
      { timeoutMs: 90000 },
    ),
  coachGuide: (id, refresh = false) =>
    getJSON(
      `/api/reports/${encodeURIComponent(id)}/coach/guide${refresh ? "?refresh=true" : ""}`,
      { timeoutMs: 90000 },
    ),
  coachNarrations: (taskId) =>
    getJSON(`/api/tasks/${encodeURIComponent(taskId)}/coach-narrations`),

  // planning session / clarify (real Manager planning; consumes model quota)
  rewriteResearchQuery: (originalQuery) =>
    postJSON(
      "/api/research-query/rewrite",
      { original_query: originalQuery },
      { timeoutMs: 90000 },
    ),
  createSession: (prompt, queryContext = {}) =>
    postJSON(
      "/api/tasks/sessions",
      {
        prompt,
        original_query: queryContext.originalQuery || prompt,
        rewritten_query: queryContext.rewrittenQuery || prompt,
        final_query: queryContext.finalQuery || prompt,
      },
      { timeoutMs: PLANNING_TIMEOUT_MS },
    ),
  createResearchRun: (prompt, queryContext = {}) =>
    postJSON(
      "/api/research/runs",
      {
        prompt,
        original_query: queryContext.originalQuery || prompt,
        rewritten_query: queryContext.rewrittenQuery || prompt,
        final_query: queryContext.finalQuery || prompt,
        workflow_mode: queryContext.workflowMode || "dynamic",
        stock_symbol: queryContext.stockSymbol || null,
        stock_name: queryContext.stockName || null,
        stock_board: queryContext.stockBoard || null,
      },
      { timeoutMs: 10000 },
    ),
  researchRunStatus: (runId) =>
    getJSON(`/api/research/runs/${encodeURIComponent(runId)}/status`),
  researchRunEventsUrl: (runId) =>
    apiBase() + `/api/research/runs/${encodeURIComponent(runId)}/events`,
  clarifySession: (taskId, answers) =>
    postJSON(
      `/api/tasks/${encodeURIComponent(taskId)}/clarify`,
      { answers },
      { timeoutMs: PLANNING_TIMEOUT_MS },
    ),
  // Absolute URL for the SSE execution stream (EventSource cannot use fetch).
  streamUrl: (taskId) =>
    apiBase() + `/api/tasks/${encodeURIComponent(taskId)}/stream`,

  // persistent local user profile
  userProfile: () => getJSON("/api/user-profile"),
  userProfileStatus: () => getJSON("/api/user-profile/status"),
  putUserProfile: (profile) =>
    requestJSON("/api/user-profile", { method: "PUT", body: profile }),
  patchUserProfile: (patch) =>
    requestJSON("/api/user-profile", { method: "PATCH", body: patch }),
  deleteUserProfile: () =>
    requestJSON("/api/user-profile", { method: "DELETE" }),
};
