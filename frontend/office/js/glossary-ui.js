// Office adapter for the shared AlphaGlossary data and persistence layer.
// Only content explicitly marked with .glossary-scope is eligible for highlighting.

let initialized = false;
let activeTerm = null;

function api() {
  return globalThis.AlphaGlossary || null;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function safeColor(value) {
  const color = String(value || "");
  return /^(?:#[0-9a-f]{3,8}|var\(--(?:amber|accent-strong|blue|cyan|green|red|yellow)\))$/i.test(color)
    ? color
    : "var(--cyan)";
}

function ensureGlossaryShell() {
  let panel = document.getElementById("glossaryPanel");
  if (panel) return panel;

  const overlay = document.createElement("div");
  overlay.id = "glossaryOverlay";
  overlay.className = "glossary-overlay";
  overlay.addEventListener("click", closeOfficeGlossary);

  panel = document.createElement("aside");
  panel.id = "glossaryPanel";
  panel.className = "glossary-panel";
  panel.setAttribute("aria-hidden", "true");
  panel.setAttribute("aria-label", "投研知识库");
  panel.innerHTML = `
    <header class="glossary-panel-head">
      <div>
        <span class="glossary-kicker">ALPHABIT COACH REFERENCE</span>
        <h2>投研知识库</h2>
      </div>
      <button class="glossary-close" type="button" title="关闭术语库" aria-label="关闭术语库">×</button>
    </header>
    <div class="glossary-panel-note">本次研究指标会自动接入。点击报告中的高亮术语，可查看公式、实际结果与局限并收藏。</div>
    <div class="glossary-knowledge-list" id="glossaryKnowledgeList"></div>
  `;
  panel.querySelector(".glossary-close").addEventListener("click", closeOfficeGlossary);
  document.body.append(overlay, panel);
  return panel;
}

function ensureTooltip() {
  let tooltip = document.getElementById("glossaryTooltip");
  if (tooltip) return tooltip;

  tooltip = document.createElement("div");
  tooltip.id = "glossaryTooltip";
  tooltip.className = "glossary-tooltip";
  tooltip.setAttribute("role", "dialog");
  tooltip.setAttribute("aria-live", "polite");
  tooltip.innerHTML = `
    <strong class="glossary-tooltip-term"></strong>
    <span class="glossary-tooltip-exp"></span>
    <button class="glossary-save-btn" type="button"></button>
  `;
  tooltip.addEventListener("mouseleave", (event) => {
    if (!event.relatedTarget?.closest?.(".glossary-term")) hideTooltip();
  });
  document.body.appendChild(tooltip);
  return tooltip;
}

function positionTooltip(tooltip, term, event) {
  const rect = term.getBoundingClientRect();
  const requestedX = event?.clientX || rect.left;
  const requestedY = event?.clientY || rect.bottom + 8;
  const width = Math.min(360, window.innerWidth - 24);
  const left = Math.max(12, Math.min(requestedX, window.innerWidth - width - 12));
  const top = Math.max(12, Math.min(requestedY + 10, window.innerHeight - 220));
  tooltip.style.width = `${width}px`;
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function showTooltip(term, event) {
  const glossary = api();
  if (!glossary || !term.closest(".glossary-scope")) return;

  activeTerm = term;
  const tooltip = ensureTooltip();
  const name = term.dataset.term || term.textContent.trim();
  const explanation = term.dataset.explanation || glossary.lookup(name)?.explanation || "";
  const color = safeColor(term.style.color);
  const saved = glossary.isKnowledgeSaved(name);

  const nameNode = tooltip.querySelector(".glossary-tooltip-term");
  nameNode.textContent = name;
  nameNode.style.color = color;
  tooltip.querySelector(".glossary-tooltip-exp").textContent = explanation;

  const saveButton = tooltip.querySelector(".glossary-save-btn");
  saveButton.textContent = saved ? "★ 已收藏" : "☆ 收藏到知识库";
  saveButton.classList.toggle("saved", saved);
  saveButton.onclick = (clickEvent) => {
    clickEvent.stopPropagation();
    if (globalThis.AlphaGlossary.isKnowledgeSaved(name)) {
      globalThis.AlphaGlossary.removeKnowledge(name);
    } else {
      globalThis.AlphaGlossary.addKnowledge(name, color, explanation);
    }
    showTooltip(term, event);
    renderKnowledgePanel();
  };

  positionTooltip(tooltip, term, event);
  tooltip.classList.add("visible");
}

function hideTooltip() {
  document.getElementById("glossaryTooltip")?.classList.remove("visible");
  activeTerm = null;
}

function renderKnowledgePanel() {
  const glossary = api();
  const list = document.getElementById("glossaryKnowledgeList");
  if (!glossary || !list) return;

  const knowledge = glossary.getKnowledge();
  if (!knowledge.length) {
    list.innerHTML = `
      <div class="glossary-empty">
        <span aria-hidden="true">◇</span>
        <strong>还没有收藏术语</strong>
        <p>在研究报告或追问结果中点击高亮术语，即可查看解释并收藏。</p>
      </div>
    `;
    return;
  }

  list.innerHTML = knowledge.map((item) => `
    <article class="glossary-card">
      <div class="glossary-card-head">
        <strong style="color:${safeColor(item.color)}">${escapeHtml(item.term)}</strong>
        <button type="button" class="glossary-remove" data-term="${escapeHtml(item.term)}" aria-label="取消收藏 ${escapeHtml(item.term)}">×</button>
      </div>
      <p>${escapeHtml(item.explanation)}</p>
    </article>
  `).join("");

  list.querySelectorAll(".glossary-remove").forEach((button) => {
    button.addEventListener("click", () => {
      globalThis.AlphaGlossary.removeKnowledge(button.dataset.term);
      renderKnowledgePanel();
      if (activeTerm) showTooltip(activeTerm);
    });
  });
}

export function highlightGlossaryScope(root) {
  const glossary = api();
  if (!glossary || !root) return;

  const scopes = [];
  if (root.classList?.contains("glossary-scope")) scopes.push(root);
  root.querySelectorAll?.(".glossary-scope").forEach((scope) => scopes.push(scope));

  if (!scopes.length && root.closest?.(".glossary-scope")) {
    glossary.highlightInDOM(root);
    return;
  }
  scopes.forEach((scope) => glossary.highlightInDOM(scope));
}

export function registerGlossaryTerms(items, root) {
  const glossary = api();
  if (!glossary) return 0;
  const added = glossary.registerTerms(items);
  if (added && root) highlightGlossaryScope(root);
  return added;
}

export function openOfficeGlossary() {
  hideTooltip();
  const panel = ensureGlossaryShell();
  const overlay = document.getElementById("glossaryOverlay");
  renderKnowledgePanel();
  overlay.classList.add("open");
  panel.classList.add("open");
  panel.setAttribute("aria-hidden", "false");
  document.getElementById("glossaryToggle")?.setAttribute("aria-expanded", "true");
  panel.querySelector(".glossary-close")?.focus();
}

export function closeOfficeGlossary() {
  const panel = document.getElementById("glossaryPanel");
  document.getElementById("glossaryOverlay")?.classList.remove("open");
  panel?.classList.remove("open");
  panel?.setAttribute("aria-hidden", "true");
  const toggle = document.getElementById("glossaryToggle");
  toggle?.setAttribute("aria-expanded", "false");
}

export function initOfficeGlossary() {
  if (initialized) return;
  initialized = true;
  ensureGlossaryShell();

  document.addEventListener("mouseover", (event) => {
    const term = event.target.closest?.(".glossary-term");
    if (term) showTooltip(term, event);
  });
  document.addEventListener("mouseout", (event) => {
    const term = event.target.closest?.(".glossary-term");
    if (!term) return;
    const related = event.relatedTarget;
    if (related?.closest?.(".glossary-tooltip, .glossary-term")) return;
    hideTooltip();
  });
  document.addEventListener("click", (event) => {
    const term = event.target.closest?.(".glossary-term");
    if (term) showTooltip(term, event);
  });
  document.addEventListener("keydown", (event) => {
    const term = event.target.closest?.(".glossary-term");
    if (term && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      showTooltip(term);
      return;
    }
    if (event.key === "Escape") {
      hideTooltip();
      closeOfficeGlossary();
    }
  });
}
