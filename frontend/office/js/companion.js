// AlphaOS Office — Companion interpretation card. Pure display-layer
// transformation: maps each Agent's structured result into a uniform
// { headline, explanation, evidence[], boundary } card shown below the
// war-room stage as steps complete. No LLM calls, no new Agent, no
// Manager/DAG changes.

// ---- helpers ----

function _pick(list, n) {
  return Array.isArray(list) ? list.slice(0, n) : [];
}

function _text(list, sep) {
  return Array.isArray(list) ? list.filter(Boolean).join(sep || "；") : "";
}

function _evidenceText(e) {
  if (typeof e === "string") return e;
  if (!e || typeof e !== "object") return "";
  if (e.detail) return e.detail;
  if (e.description) return e.description;
  if (e.content) return e.content;
  if (e.name && e.value != null) return `${e.name}：${e.value}${e.unit || ""}`;
  if (e.indicator != null && e.value != null) return `${e.indicator}：${e.value}${e.unit || ""}`;
  if (e.text) return e.text;
  if (e.title) return e.title;
  if (e.summary) return e.summary;
  if ((e.type === "skill_result" || e.type === "macro_result") && e.data) {
    const d = e.data;
    if (d.overall_assessment && d.overall_assessment.fact_count != null) {
      return `${d.symbol || d.ticker || ""} 完成：${d.overall_assessment.fact_count} 项事实，${d.overall_assessment.derived_metric_count} 项衍生指标`;
    }
    if (d.conclusion) return d.conclusion;
    if (d.summary) return d.summary;
    const vals = Object.values(d).filter((v) => typeof v === "string" && v.length > 5);
    if (vals.length) return vals[0];
  }
  const vals = Object.values(e).filter((v) => typeof v === "string" && v.length > 5);
  return vals.length ? vals[0] : "";
}

function _evidence(list, n) {
  return _pick(list, n).map((e) => _evidenceText(e)).filter(Boolean);
}

// Craft a short headline (≤30 chars if possible): "做了什么：结论"
function _brief(summary, fallbackList) {
  if (summary && summary.length <= 35) return summary;
  // try to find a concise signal in fallbackList
  for (const item of fallbackList) {
    if (typeof item === "string" && item.length > 4 && item.length <= 35) return item;
  }
  // truncate summary to ~30 chars
  if (summary) return summary.slice(0, 30) + "…";
  return "";
}

// ---- public API ----

export function companionAdapter(agentId, meta) {
  if (!meta || (!meta.result_summary && !meta.evidence?.length && !meta.risks?.length)) {
    return null;
  }
  const fn = ADAPTERS[agentId] || ADAPTERS._default;
  return fn(meta);
}

const ADAPTERS = {
  research(meta) {
    const summary = meta.result_summary || "";
    const evidence = _evidence(meta.evidence, 3);
    const boundary = _text([
      ..._pick(meta.assumptions, 2).map((a) => `假设：${a}`),
      ..._pick(meta.risks, 2).map((r) => `风险：${r}`),
      ..._pick(meta.limitations, 1).map((l) => `局限：${l}`),
    ]);
    return {
      headline: _brief(summary, evidence) || "完成了基本面研究与分析",
      explanation: evidence.length
        ? `基于 ${evidence.length} 项分析依据：${evidence[0]}`
        : "基于基本面数据与行业研究框架综合判断。",
      evidence,
      boundary: boundary || "以上结论基于当前可得数据，不构成投资建议。",
    };
  },

  quant(meta) {
    const summary = meta.result_summary || "";
    const evidence = _evidence(meta.evidence, 3);
    const boundary = _text([
      ..._pick(meta.assumptions, 2).map((a) => `假设：${a}`),
      ..._pick(meta.risks, 1).map((r) => `风险：${r}`),
      ..._pick(meta.limitations, 1).map((l) => `局限：${l}`),
    ]);
    return {
      headline: _brief(summary, evidence) || "完成了量化模型计算",
      explanation: evidence.length
        ? `量化模型计算结果：${evidence[0]}`
        : "基于历史市场数据与因子模型计算得出。",
      evidence,
      boundary: boundary || "以上结果基于历史数据，因子有效性需持续验证，不构成投资建议。",
    };
  },

  risk(meta) {
    const summary = meta.result_summary || "";
    const risks = _pick(meta.risks, 3);
    const evidence = _evidence(meta.evidence, 3);
    const boundary = _text([
      ..._pick(meta.assumptions, 1).map((a) => `假设：${a}`),
      ..._pick(meta.limitations, 2).map((l) => `局限：${l}`),
    ]);
    return {
      headline: _brief(summary, risks) || `识别到 ${risks.length} 项关键风险`,
      explanation: risks.length
        ? `主要风险：${risks.join("；")}`
        : "通过事件驱动与压力测试方法完成风险评估。",
      evidence: evidence.length ? evidence : risks.map((r) => `风险项：${r}`),
      boundary: boundary || "风险识别基于已知事件数据，未覆盖情景可能未被识别，不构成完整风控意见。",
    };
  },

  macro(meta) {
    const summary = meta.result_summary || "";
    const evidence = _evidence(meta.evidence, 3);
    const boundary = _text([
      ..._pick(meta.assumptions, 2).map((a) => `假设：${a}`),
      ..._pick(meta.limitations, 1).map((l) => `局限：${l}`),
    ]);
    return {
      headline: _brief(summary, evidence) || "完成了宏观环境研判",
      explanation: evidence.length
        ? `关键驱动因素：${evidence[0]}`
        : "基于宏观经济数据与政策环境分析得出。",
      evidence,
      boundary: boundary || "宏观预测受多重不确定性影响，仅供参考，不构成投资依据。",
    };
  },

  report(meta) {
    const summary = meta.result_summary || "";
    const evidence = _evidence(meta.evidence, 3);
    const boundary = _text([
      ..._pick(meta.assumptions, 1).map((a) => `假设：${a}`),
      ..._pick(meta.limitations, 2).map((l) => `局限：${l}`),
    ]);
    return {
      headline: _brief(summary, evidence) || "完成了多方研究整合",
      explanation: evidence.length
        ? `报告整合自 ${evidence.length} 项关键依据`
        : "已整合多方研究结论，形成结构化报告。",
      evidence,
      boundary: boundary || "本报告由 AI 自动生成，仅供参考学习，不构成投资建议。",
    };
  },

  _default(meta) {
    const summary = meta.result_summary || "";
    return {
      headline: _brief(summary, []) || "分析已完成",
      explanation: "专家已完成指定分析任务。",
      evidence: _evidence(meta.evidence, 2),
      boundary: _text([
        ..._pick(meta.risks, 1).map((r) => `风险：${r}`),
        ..._pick(meta.limitations, 1).map((l) => `局限：${l}`),
      ]) || "以上结果仅供参考，不构成投资建议。",
    };
  },
};

// ---- DOM renderer ----

const CARD_ICONS = {
  headline: "🔍",
  explanation: "💡",
  evidence: "📋",
  boundary: "⚠️",
};

export function renderCompanionCard(container, data) {
  if (!data) return;

  const card = document.createElement("div");
  card.className = "companion-card";

  const inner = document.createElement("div");
  inner.className = "companion-inner";

  if (data.headline) {
    const section = _section(CARD_ICONS.headline, "一句话看懂", data.headline, "companion-headline");
    inner.appendChild(section);
  }

  if (data.explanation) {
    const section = _section(CARD_ICONS.explanation, "为什么这样判断", data.explanation, "companion-explanation");
    inner.appendChild(section);
  }

  if (data.evidence && data.evidence.length > 0) {
    const section = _section(CARD_ICONS.evidence, "判断依据", "", "companion-evidence");
    const list = document.createElement("ul");
    list.className = "companion-evidence-list";
    data.evidence.filter(Boolean).forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item;
      list.appendChild(li);
    });
    section.appendChild(list);
    inner.appendChild(section);
  }

  if (data.boundary) {
    const section = _section(CARD_ICONS.boundary, "需要注意", data.boundary, "companion-boundary");
    inner.appendChild(section);
  }

  card.appendChild(inner);
  container.appendChild(card);
  container.scrollTop = container.scrollHeight;
  return card;
}

function _section(icon, label, text, cls) {
  const div = document.createElement("div");
  div.className = `companion-section ${cls}`;
  const title = document.createElement("div");
  title.className = "companion-section-title";
  title.textContent = icon + " " + label;
  div.appendChild(title);
  if (text) {
    const p = document.createElement("p");
    p.className = "companion-text";
    p.textContent = text;
    div.appendChild(p);
  }
  return div;
}
