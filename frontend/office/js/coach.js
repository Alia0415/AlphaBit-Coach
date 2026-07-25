// AlphaBit Coach — 陪练层前端组件（报告陪练侧边栏 + 投研课堂面板）。
// Coach 不是专家，也不进入任务 DAG：它只读已完成报告、执行事件与用户画像。
// 所有模型产出都带「模型生成」标识；模型失败时如实展示错误，绝不降级编造。

// ---- tiny DOM helpers (kept local so this module has no app.js dependency) --

function el(tag, cls, html) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (html !== undefined) node.innerHTML = html;
  return node;
}

function esc(str) {
  return String(str ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function nowClock() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

const clip = (text, max = 60) => {
  const s = String(text ?? "");
  return s.length > max ? `${s.slice(0, max)}…` : s;
};

const MODEL_BADGE = '<span class="coach-badge model">模型生成</span>';
const DEMO_BADGE = '<span class="coach-badge demo">示例</span>';
const EVIDENCE_BADGE = '<span class="coach-badge evidence">证据检索 · 未调模型</span>';

// 分区折叠状态在同一页面会话内记住（buildCoachSidebar 每份报告都会重建）。
const FOLD_STATE = new Map();

// ---- coach message rendering ------------------------------------------------

function renderCoachMessage(m) {
  if (m.role === "sys") {
    return el("div", "coach-msg sys", `
      <div class="coach-bubble sys">${esc(m.text)}</div>`);
  }
  if (m.role === "user") {
    const node = el("div", "coach-msg me");
    if (m.quoted_text) {
      node.appendChild(el(
        "div",
        "coach-quote-ref",
        `❝ ${esc(clip(m.quoted_text, 80))}`,
      ));
    }
    node.appendChild(el("div", "coach-bubble me", esc(m.text)));
    node.appendChild(el("div", "coach-meta", `你 · ${esc(m.time || "")}`));
    return node;
  }

  // coach / evidence replies
  const node = el("div", "coach-msg bot");
  const badge = m.role === "evidence"
    ? EVIDENCE_BADGE
    : (m.demo ? DEMO_BADGE : MODEL_BADGE);
  node.appendChild(el(
    "div",
    "coach-meta",
    `陪练 · ${esc(m.time || "")} ${badge}`,
  ));
  if (m.error) {
    node.appendChild(el("div", "coach-bubble error", esc(m.text)));
    return node;
  }
  node.appendChild(el("div", "coach-bubble", esc(m.text)));

  if (Array.isArray(m.concept_notes) && m.concept_notes.length) {
    const cards = el("div", "coach-terms");
    cards.appendChild(el("div", "coach-inline-title", "术语解释"));
    m.concept_notes.forEach((n) => {
      cards.appendChild(el(
        "div",
        "coach-term-card",
        `<strong>${esc(n.term)}</strong><span>${esc(n.explanation)}</span>`,
      ));
    });
    node.appendChild(cards);
  }
  if (Array.isArray(m.cited_evidence) && m.cited_evidence.length) {
    const cites = el("div", "coach-cites");
    cites.appendChild(el("div", "coach-cites-title", "引用的报告原文"));
    m.cited_evidence.forEach((c) => {
      cites.appendChild(el("div", "coach-cite", `❝ ${esc(c)}`));
    });
    node.appendChild(cites);
  }
  if (Array.isArray(m.evidence) && m.evidence.length) {
    const cites = el("div", "coach-cites");
    cites.appendChild(el("div", "coach-cites-title", "检索到的证据"));
    m.evidence.forEach((e) => {
      cites.appendChild(el(
        "div",
        "coach-cite",
        `<b>${esc(e.source || "证据")}</b>：${esc(clip(e.text, 160))}`,
      ));
    });
    node.appendChild(cites);
  }
  if (m.uncertainty_note) {
    node.appendChild(el("div", "coach-uncertain", `⚠ ${esc(m.uncertainty_note)}`));
  }
  return node;
}

function mapSeedMessage(m) {
  return {
    role: m.role === "user" ? "user" : "coach",
    text: m.text || "",
    quoted_text: m.quoted_text || null,
    concept_notes: m.concept_notes || [],
    cited_evidence: m.cited_evidence || [],
    uncertainty_note: m.uncertainty_note || "",
    demo: !!m.demo,
    time: (m.created_at || "").slice(11, 19),
  };
}

// ---- guide (research review + guided questions) ------------------------------

function renderGuide(guide, { demo, onPick, onRefresh }) {
  const box = el("div", "coach-guide");
  const review = guide.review || {};
  const head = el("div", "coach-guide-head");
  // 分区标题已由外层折叠栏提供，这里只保留来源标识与刷新入口
  head.appendChild(el("span", "", demo ? DEMO_BADGE : MODEL_BADGE));
  const refresh = el("button", "coach-guide-refresh", "↻ 重新生成");
  refresh.title = "重新调用模型生成复盘与思考题";
  refresh.addEventListener("click", onRefresh);
  head.appendChild(refresh);
  box.appendChild(head);

  if (review.framework) {
    box.appendChild(el("div", "coach-guide-row", `<b>研究框架</b>${esc(review.framework)}`));
  }
  if (Array.isArray(review.experts_involved) && review.experts_involved.length) {
    box.appendChild(el(
      "div",
      "coach-guide-row",
      `<b>参与专家</b>${esc(review.experts_involved.join("、"))}`,
    ));
  }
  const listRow = (label, items) => {
    if (!Array.isArray(items) || !items.length) return;
    box.appendChild(el(
      "div",
      "coach-guide-row",
      `<b>${label}</b>${items.map((t) => `<span>· ${esc(t)}</span>`).join("")}`,
    ));
  };
  listRow("结论依据", review.evidence_basis);
  listRow("未解决问题", review.open_questions);
  listRow("下一步学什么", review.next_learning_steps);

  const qs = Array.isArray(guide.guided_questions) ? guide.guided_questions : [];
  if (qs.length) {
    box.appendChild(el("div", "coach-guide-sub", "值得想一想"));
    const chips = el("div", "coach-guide-chips");
    qs.forEach((q) => {
      const chip = el("button", "coach-qchip", esc(q.question));
      chip.title = q.why_it_matters || "";
      chip.addEventListener("click", () => onPick(q.question));
      chips.appendChild(chip);
    });
    box.appendChild(chips);
  }
  return box;
}

// ---- coach sidebar ------------------------------------------------------------

// options:
//   seedMessages : persisted CoachMessage list (live) / [] (demo)
//   loadGuide(refresh) -> Promise<CoachGuide>
//   ask(question, quotedText) -> Promise<CoachMessage>
//   evidence(question) -> Promise<{text, evidence, created_at}> | null（关闭次级通道）
//   demo : true 时所有产出标注「示例」
//   sectionContexts : 当前报告的动态章节，只包含本次真实研究生成的内容
//   onCollapseChange(collapsed) : 页面据此调整栅格布局
export function buildCoachSidebar(options) {
  const {
    seedMessages = [],
    sectionContexts = [],
    loadGuide,
    ask,
    evidence,
    demo = false,
  } = options;
  const wrap = el("div", "coach-side");
  const panel = el("aside", "panel coach-panel glossary-scope");
  wrap.appendChild(panel);

  // header
  const head = el("div", "coach-head");
  const headTitle = el(
    "div",
    "coach-head-title",
    "<strong>🎓 AlphaBit Coach 陪练</strong>",
  );
  const readingLabel = el("small", "coach-reading-label", "正在陪练 · 结论速览");
  headTitle.appendChild(readingLabel);
  head.appendChild(headTitle);
  const collapseBtn = el("button", "coach-collapse-btn", "⇥");
  collapseBtn.title = "折叠陪练侧边栏";
  head.appendChild(collapseBtn);
  panel.appendChild(head);

  // 可折叠分区：分区标题即开关，收起不常用区块可以给对话流让出空间
  const makeFold = (key, label, target, { open = true } = {}) => {
    const head = el("button", "coach-section-label coach-fold-toggle");
    head.type = "button";
    const title = el("span", "coach-fold-title", esc(label));
    const arrow = el("span", "coach-fold-arrow");
    head.append(title, arrow);
    let opened = FOLD_STATE.has(key) ? FOLD_STATE.get(key) : open;
    const setOpen = (next) => {
      opened = next;
      FOLD_STATE.set(key, next);
      target.classList.toggle("folded", !next);
      arrow.textContent = next ? "▾" : "▸";
      head.title = next ? "收起该分区" : "展开该分区";
    };
    head.addEventListener("click", () => setOpen(!opened));
    setOpen(opened);
    return {
      head,
      setOpen,
      isOpen: () => opened,
      setLabel: (text) => { title.textContent = text; },
    };
  };

  // current report section: deterministic teaching cues from the real view model
  const contextSlot = el("div", "coach-reading-slot");
  const readingFold = makeFold("reading", "本节导读", contextSlot);
  panel.appendChild(readingFold.head);
  panel.appendChild(contextSlot);

  // guide slot（默认收起为标签栏，展开后再看复盘与思考题）
  const guideSlot = el("div", "coach-guide-slot");
  const guideFold = makeFold("guide", "研究复盘", guideSlot, { open: false });
  panel.appendChild(guideFold.head);
  panel.appendChild(guideSlot);

  // chat stream
  const chatSection = el("div", "coach-chat-section");
  const chatFold = makeFold("chat", "对话记录", chatSection);
  chatSection.appendChild(chatFold.head);
  const scroll = el("div", "coach-scroll");
  chatSection.appendChild(scroll);
  panel.appendChild(chatSection);
  const toBottom = () => { scroll.scrollTop = scroll.scrollHeight; };
  const push = (m) => {
    const node = renderCoachMessage(m);
    scroll.appendChild(node);
    toBottom();
    return node;
  };

  push({
    role: "sys",
    text: demo
      ? "这里是示例陪练对话：Live 模式下陪练会基于真实报告证据用模型讲解。"
      : "你可以就报告中的数据、术语、结论提问，也可以在正文中选中文字后引用提问。",
  });
  seedMessages.forEach((m) => push({ ...mapSeedMessage(m), demo: demo || !!m.demo }));

  // quote chip bar
  let quotedText = null;
  const compose = el("div", "coach-compose");
  compose.appendChild(el("div", "coach-section-label", "提问区"));
  compose.appendChild(el(
    "p",
    "coach-quote-hint",
    "选中左侧报告文字，可带着原文一起提问。",
  ));
  const quoteBar = el("div", "coach-quotebar");
  quoteBar.style.display = "none";
  const setQuote = (text) => {
    quotedText = text || null;
    quoteBar.innerHTML = "";
    if (!quotedText) { quoteBar.style.display = "none"; return; }
    const chip = el("span", "coach-quote-chip", `❝ ${esc(clip(quotedText, 48))}`);
    const remove = el("button", "coach-quote-x", "✕");
    remove.title = "移除引用";
    remove.addEventListener("click", () => setQuote(null));
    chip.appendChild(remove);
    quoteBar.appendChild(chip);
    quoteBar.style.display = "";
    input.focus();
  };

  // mode toggle: 陪练问答（调模型） / 只查证据（不调模型）
  let mode = "coach";
  const modeBar = el("div", "coach-modebar");
  const coachMode = el("button", "coach-mode sel", "陪练问答 · 调模型");
  const evidenceMode = el("button", "coach-mode", "只查证据 · 不调模型");
  const applyMode = (next) => {
    mode = next;
    coachMode.classList.toggle("sel", mode === "coach");
    evidenceMode.classList.toggle("sel", mode === "evidence");
    input.placeholder = mode === "coach"
      ? "问报告里的数据、术语或结论…"
      : "输入问题，只检索报告已有证据…";
  };
  coachMode.addEventListener("click", () => applyMode("coach"));
  evidenceMode.addEventListener("click", () => applyMode("evidence"));
  modeBar.append(coachMode, evidenceMode);

  // input bar
  const inputBar = el("div", "chat-inputbar coach-inputbar");
  const input = el("input");
  input.type = "text";
  const send = el("button", "btn btn-primary", "➤");
  inputBar.append(input, send);
  compose.append(quoteBar, modeBar, inputBar);
  panel.appendChild(compose);
  applyMode("coach");

  const contexts = new Map(
    sectionContexts
      .filter((item) => item && item.id)
      .map((item) => [item.id, item]),
  );
  let currentContextId = "";
  const setContext = (id) => {
    const context = contexts.get(id) || sectionContexts[0];
    if (!context || (currentContextId === context.id && contextSlot.childElementCount)) return;
    currentContextId = context.id;
    readingLabel.textContent = `正在陪练 · ${context.label}`;
    readingFold.setLabel(`本节导读 · ${context.label}`);
    contextSlot.innerHTML = "";
    const card = el("section", "coach-reading-card");
    const rows = [
      ["一句话读懂", context.summary],
      ["本节学习重点", context.learningFocus],
      ["常见误区", context.misconception],
    ].filter(([, value]) => value);
    rows.forEach(([label, value]) => {
      const row = el("div", "coach-reading-row");
      row.appendChild(el("strong", "", esc(label)));
      row.appendChild(el("p", "", esc(value)));
      card.appendChild(row);
    });
    const questions = (context.questions || []).filter(Boolean).slice(0, 3);
    if (questions.length) {
      const questionWrap = el("div", "coach-reading-questions");
      questionWrap.appendChild(el("strong", "", "相关追问建议"));
      questions.forEach((question) => {
        const chip = el("button", "coach-reading-question", esc(question));
        chip.type = "button";
        chip.addEventListener("click", () => {
          input.value = question;
          input.focus();
        });
        questionWrap.appendChild(chip);
      });
      card.appendChild(questionWrap);
    }
    contextSlot.appendChild(card);
  };
  setContext(sectionContexts[0]?.id);

  let busy = false;
  const fire = () => {
    const q = input.value.trim();
    if (!q || busy) return;
    input.value = "";
    busy = true;
    if (!chatFold.isOpen()) chatFold.setOpen(true);
    const quote = mode === "coach" ? quotedText : null;
    push({ role: "user", text: q, quoted_text: quote, time: nowClock() });
    if (quote) setQuote(null);
    const typing = push({
      role: "sys",
      text: mode === "coach" ? "陪练正在结合报告证据思考…" : "正在检索报告证据…",
    });
    const done = () => { busy = false; typing.remove(); };
    if (mode === "evidence" && evidence) {
      evidence(q)
        .then((ans) => {
          done();
          push({
            role: "evidence",
            text: ans.text || "",
            evidence: ans.evidence || [],
            time: (ans.created_at || "").slice(11, 19) || nowClock(),
          });
        })
        .catch((err) => {
          done();
          push({ role: "coach", error: true, time: nowClock(),
            text: err?.message || "证据检索暂时不可用，请稍后重试。" });
        });
      return;
    }
    ask(q, quote)
      .then((msg) => {
        done();
        push({ ...mapSeedMessage(msg), demo, time: mapSeedMessage(msg).time || nowClock() });
      })
      .catch((err) => {
        done();
        push({ role: "coach", error: true, time: nowClock(),
          text: err?.message || "陪练暂时不可用，请稍后重试。" });
      });
  };
  send.addEventListener("click", fire);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") fire(); });

  // guide lifecycle
  const mountGuide = (refresh) => {
    guideSlot.innerHTML = "";
    guideSlot.appendChild(el("div", "coach-guide-loading", "复盘与思考题生成中…"));
    loadGuide(refresh)
      .then((guide) => {
        guideSlot.innerHTML = "";
        guideSlot.appendChild(renderGuide(guide, {
          demo,
          onPick: (q) => { input.value = q; input.focus(); },
          onRefresh: () => mountGuide(true),
        }));
      })
      .catch((err) => {
        guideSlot.innerHTML = "";
        const fail = el(
          "div",
          "coach-guide-loading error",
          esc(err?.message || "复盘生成失败。"),
        );
        const retry = el("button", "coach-guide-refresh", "重试");
        retry.addEventListener("click", () => mountGuide(false));
        fail.appendChild(retry);
        guideSlot.appendChild(fail);
      });
  };
  if (loadGuide) mountGuide(false);
  else { guideFold.head.remove(); guideSlot.remove(); }

  // collapse / expand（窄屏折叠为悬浮按钮）
  const fab = el("button", "coach-fab", "🎓");
  fab.title = "展开 AI 金融陪练";
  fab.style.display = "none";
  wrap.appendChild(fab);
  const setCollapsed = (collapsed) => {
    panel.style.display = collapsed ? "none" : "";
    fab.style.display = collapsed ? "" : "none";
    wrap.classList.toggle("collapsed", collapsed);
    options.onCollapseChange && options.onCollapseChange(collapsed);
  };
  collapseBtn.addEventListener("click", () => setCollapsed(true));
  fab.addEventListener("click", () => setCollapsed(false));

  requestAnimationFrame(toBottom);
  return { root: wrap, setQuote, setContext };
}

// ---- selection quoting（类 IDE「add selection to chat」）-----------------------

// 监听报告正文选区：选中非空文本时在选区旁显示「引用并提问」悬浮按钮。
// 返回 destroy() 供页面卸载时清理 document 级监听。
export function attachSelectionQuoting(container, onQuote) {
  const btn = el("button", "coach-select-btn", "❝ 引用并提问");
  btn.style.display = "none";
  document.body.appendChild(btn);
  let current = "";

  const hide = () => { btn.style.display = "none"; current = ""; };
  const onMouseUp = () => {
    setTimeout(() => {
      const sel = window.getSelection();
      const text = sel ? String(sel).trim() : "";
      if (!text || text.length > 500 || !sel.rangeCount) { hide(); return; }
      const range = sel.getRangeAt(0);
      if (!container.contains(range.commonAncestorContainer)) { hide(); return; }
      const rect = range.getBoundingClientRect();
      btn.style.left = `${Math.max(8, rect.left + window.scrollX)}px`;
      btn.style.top = `${rect.bottom + window.scrollY + 6}px`;
      btn.style.display = "";
      current = text;
    }, 0);
  };
  const onMouseDown = (e) => { if (e.target !== btn) hide(); };
  container.addEventListener("mouseup", onMouseUp);
  document.addEventListener("mousedown", onMouseDown);
  btn.addEventListener("click", () => {
    if (current) onQuote(current);
    hide();
    const sel = window.getSelection();
    if (sel) sel.removeAllRanges();
  });

  return {
    destroy() {
      btn.remove();
      container.removeEventListener("mouseup", onMouseUp);
      document.removeEventListener("mousedown", onMouseDown);
    },
  };
}

// ---- 投研课堂（过程陪练解说面板） ---------------------------------------------

const MILESTONE_LABEL = {
  plan_created: "计划建立",
  step_completed: "步骤完成",
  step_failed: "步骤失败",
  task_completed: "任务收官",
};

// 可折叠的作战室「投研课堂」面板。解说由后端模型异步生成，到达有延迟属正常。
// push() 按 seq 去重排序；finish() 在任务结束后清理等待态。
export function createClassroomPanel({ demo = false, agentName } = {}) {
  const root = el("div", "panel classroom-panel");
  const head = el("div", "classroom-head");
  head.appendChild(el(
    "div",
    "",
    `<strong>🏫 投研课堂</strong><small>过程解说 ${demo ? "· 示例" : "· 模型生成"}</small>`,
  ));
  const toggle = el("button", "coach-collapse-btn", "▾");
  head.appendChild(toggle);
  root.appendChild(head);

  const feed = el("div", "classroom-feed");
  root.appendChild(feed);
  const waiting = el(
    "div",
    "classroom-waiting",
    demo
      ? "示例解说播放中…"
      : "解说生成中…（模型解说会比执行进度稍有延迟）",
  );
  feed.appendChild(waiting);

  toggle.addEventListener("click", () => {
    const hidden = feed.style.display === "none";
    feed.style.display = hidden ? "" : "none";
    toggle.textContent = hidden ? "▾" : "▸";
  });

  const seen = new Set();
  const push = (n) => {
    const seq = n.seq ?? seen.size + 1;
    if (seen.has(seq)) return;
    seen.add(seq);
    const item = el("div", "classroom-item");
    item.dataset.seq = String(seq);
    const who = n.agent && agentName ? agentName(n.agent) : (n.agent || "");
    item.innerHTML = `
      <div class="classroom-item-head">
        <span class="classroom-milestone">${esc(MILESTONE_LABEL[n.milestone] || n.milestone || "")}</span>
        ${who ? `<span class="classroom-agent">${esc(who)}</span>` : ""}
        ${demo ? DEMO_BADGE : MODEL_BADGE}
      </div>
      <p class="classroom-narration">${esc(n.narration || "")}</p>
      <p class="classroom-teaching">💡 ${esc(n.teaching_point || "")}</p>
    `;
    // keep items ordered by seq even if async narrations arrive out of order
    const next = [...feed.querySelectorAll(".classroom-item")]
      .find((node) => Number(node.dataset.seq) > seq);
    feed.insertBefore(item, next || null);
    feed.scrollTop = feed.scrollHeight;
  };

  const finish = () => {
    waiting.remove();
    if (!seen.size) {
      feed.appendChild(el(
        "div",
        "classroom-waiting",
        "本次任务没有生成课堂解说。",
      ));
    }
  };

  return { root, push, finish };
}
