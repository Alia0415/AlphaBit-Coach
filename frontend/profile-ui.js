(function attachProfileUI(root) {
  "use strict";

  const model = root.AlphaOSUserProfile;
  if (!model) throw new Error("AlphaOSUserProfile must load before profile-ui.js");

  const FIELD_LABELS = {
    investment_goal: "投资目标",
    investment_horizon_months: "投资期限",
    liquidity_need: "流动性需求",
    monthly_after_tax_income_cny: "每月税后收入",
    monthly_essential_expenses_cny: "每月必要支出",
    monthly_debt_payment_cny: "每月债务还款",
    emergency_fund_cny: "应急资金",
    planned_large_expenses_cny: "计划大额支出",
    planned_large_expenses_within_months: "大额支出时间",
    available_investment_funds_cny: "可投资资金",
    max_acceptable_loss_ratio: "最大可接受亏损",
    investment_experience: "投资经验",
    existing_positions: "当前持仓",
  };
  const LIQUIDITY_LABELS = {
    high: "高：可能随时需要",
    medium: "中：一年内可能需要",
    low: "低：几年内基本不会使用",
  };
  const EXPERIENCE_LABELS = {
    none: "没有实际投资经验",
    basic: "有基础经验",
    experienced: "有较多实际经验",
  };
  const STEPS = [
    {
      key: "investment_goal",
      title: "你希望这笔投资主要解决什么问题？",
      why: "目标会帮助后续研究聚焦正确的时间尺度和证据，不会被用来自动生成买卖建议。",
      example: "例如资产保值、长期增值、购房准备、教育支出或退休储备。",
      field: () =>
        fieldMarkup("investment_goal", "textarea", {
          placeholder: "例如：为 5 年后的购房首付做准备",
        }),
    },
    {
      key: "monthly_after_tax_income_cny",
      title: "你每月实际到手的收入大约是多少？",
      why: "税后收入与必要支出、还款一起，能确定性计算每月结余。",
      example: "金额不需要非常精确，例如每月约 15,000 元。",
      field: () => moneyMarkup("monthly_after_tax_income_cny"),
    },
    {
      key: "monthly_essential_expenses_cny",
      title: "你每月必须支付的生活费用大约是多少？",
      why: "必要支出用于计算每月结余，以及应急资金能覆盖多少个月。",
      example: "可包括房租或房贷、基本生活、交通、医疗和家庭支出。",
      field: () => moneyMarkup("monthly_essential_expenses_cny"),
    },
    {
      key: "monthly_debt_payment_cny",
      title: "除日常支出外，你每月是否还有固定还款？",
      why: "固定还款会减少可自由支配的现金，也反映现实债务负担。",
      example: "例如房贷、车贷、消费贷或信用卡分期；没有可填写 0 元。",
      field: () => moneyMarkup("monthly_debt_payment_cny"),
    },
    {
      key: "planned_large_expenses_cny",
      fields: [
        "planned_large_expenses_cny",
        "planned_large_expenses_within_months",
      ],
      title: "未来 12 个月内，你是否有确定的大额支出？",
      why: "近期确定支出会影响这笔资金可使用的期限和流动性约束。",
      example: "例如学费、购房首付、装修、婚礼或医疗；没有可把金额填为 0。",
      field: () =>
        `${moneyMarkup("planned_large_expenses_cny", "大致金额")}
         ${numberMarkup(
           "planned_large_expenses_within_months",
           "预计几个月内发生",
           0,
           1200,
         )}`,
    },
    {
      key: "emergency_fund_cny",
      title: "目前你有多少资金可以专门应对失业、疾病或紧急支出？",
      why: "通常可以用“能覆盖几个月必要支出”来理解应急资金，这部分不包括计划投入市场的钱。",
      example: "例如必要支出每月 8,000 元、应急资金 48,000 元，约覆盖 6 个月。",
      field: () => moneyMarkup("emergency_fund_cny"),
    },
    {
      key: "available_investment_funds_cny",
      title: "在不影响日常生活和应急资金的前提下，这次你计划投入多少资金？",
      why: "这里记录的是用户明确确认的资金范围，不会被系统自动放大或补齐。",
      example: "例如计划投入约 100,000 元；暂不确定也可以稍后填写。",
      field: () => moneyMarkup("available_investment_funds_cny"),
    },
    {
      key: "investment_horizon_months",
      title: "这笔钱最早可能在什么时候需要使用？",
      why: "投资期限是现实约束，不能由投资经验或亏损意愿替代。",
      example: "例如 6 个月、2 年（24 个月）或 5 年以上（60 个月以上）。",
      field: () =>
        numberMarkup("investment_horizon_months", "投资期限（月）", 1, 1200),
    },
    {
      key: "liquidity_need",
      title: "如果出现临时需要，你是否必须很快取回这笔钱？",
      why: "流动性需求描述资金必须多快可用，与愿意承受多少波动是两件事。",
      example: "高：可能随时需要；中：一年内可能需要；低：几年内基本不会使用。",
      field: () =>
        selectMarkup("liquidity_need", "请选择", LIQUIDITY_LABELS),
    },
    {
      key: "max_acceptable_loss_ratio",
      title: "假设投入 10 万元，短期下跌多少会明显影响生活或让你必须卖出？",
      why: "这只是了解你的承受边界，不代表系统建议承担该亏损，也不会据此自动生成风险等级。",
      example: "5,000 元 = 5%；1 万元 = 10%；2 万元 = 20%；3 万元 = 30%。",
      field: () => percentMarkup("max_acceptable_loss_ratio"),
    },
    {
      key: "existing_positions",
      title: "你目前有哪些存款、基金、股票、债券或其他投资？",
      why: "持仓事实可用于确定性计算已知集中度；未回答和明确没有持仓会分别保存。",
      example: "每项可填写大致金额或占总投资资产的比例，不要求账号或产品流水。",
      field: () => positionsMarkup([], "onboarding"),
    },
    {
      key: "investment_experience",
      title: "你过去是否实际购买和持有过股票、基金、债券等产品？",
      why: "经验仅记录事实，系统不会仅凭经验判断你适合承担更高风险。",
      example: "没有实际购买经历可选“没有”；少量基金或股票经历可选“基础”。",
      field: () =>
        selectMarkup("investment_experience", "请选择", EXPERIENCE_LABELS),
    },
  ];

  let profile = null;
  let onboardingDraft = null;
  let onboardingStep = 0;
  const elements = {};

  function init() {
    [
      "researchNavButton",
      "profileNavButton",
      "profileCompletenessBadge",
      "profilePage",
      "profilePageContent",
      "onboardingOverlay",
      "onboardingContent",
      "profileToast",
    ].forEach((id) => {
      elements[id] = document.getElementById(id);
    });
    if (!elements.profilePage || !elements.onboardingOverlay) return;

    const loaded = model.loadProfile(root.localStorage);
    profile = loaded.profile;
    bindEvents();
    renderProfileBadge();
    renderProfilePage();
    if (loaded.reset) {
      showToast(`${loaded.error || "画像数据无效"}，请重新建档。`, "error");
    }
    if (model.shouldStartOnboarding(profile)) openOnboarding();
  }

  function bindEvents() {
    elements.researchNavButton?.addEventListener("click", () => setPage("research"));
    elements.profileNavButton?.addEventListener("click", () => setPage("profile"));
    elements.profilePage.addEventListener("click", handleProfilePageClick);
    elements.onboardingOverlay.addEventListener("click", handleOnboardingClick);
  }

  function getProfile() {
    return profile && profile.onboarding_completed
      ? JSON.parse(JSON.stringify(profile))
      : null;
  }

  function setPage(page) {
    const showProfile = page === "profile";
    document.querySelectorAll("main > section").forEach((section) => {
      section.hidden = showProfile
        ? section.id !== "profilePage"
        : section.id === "profilePage";
    });
    elements.researchNavButton?.classList.toggle("active", !showProfile);
    elements.profileNavButton?.classList.toggle("active", showProfile);
    if (showProfile) renderProfilePage();
  }

  function openOnboarding() {
    onboardingDraft = JSON.parse(
      JSON.stringify(profile || model.createEmptyProfile()),
    );
    onboardingDraft.onboarding_completed = false;
    onboardingStep = 0;
    elements.onboardingOverlay.hidden = false;
    document.body.classList.add("modal-open");
    renderOnboarding();
  }

  function closeOnboarding() {
    elements.onboardingOverlay.hidden = true;
    document.body.classList.remove("modal-open");
  }

  function renderOnboarding() {
    if (onboardingStep >= STEPS.length) {
      renderOnboardingSummary();
      return;
    }
    const step = STEPS[onboardingStep];
    const fields = step.fields || [step.key];
    let markup = step.field();
    elements.onboardingContent.innerHTML = `
      <div class="onboarding-progress" aria-label="建档进度">
        <span>首次画像建档</span>
        <strong>${onboardingStep + 1} / ${STEPS.length}</strong>
        <div><i style="width:${((onboardingStep + 1) / STEPS.length) * 100}%"></i></div>
      </div>
      <div class="onboarding-question">
        <span class="question-kicker">MANAGER · PROFILE MODE</span>
        <h2>${step.title}</h2>
        <p class="question-why">${step.why}</p>
        <p class="question-example">${step.example}</p>
        <div class="onboarding-fields" data-fields="${fields.join(",")}">${markup}</div>
        <div class="profile-form-error" id="onboardingError" role="alert"></div>
      </div>
      <div class="onboarding-actions">
        <button type="button" class="ghost-button" data-onboarding="back" ${
          onboardingStep === 0 ? "disabled" : ""
        }>上一步</button>
        <button type="button" class="text-button" data-onboarding="skip">暂时不确定，稍后填写</button>
        <button type="button" class="primary-button" data-onboarding="next">保存并继续</button>
      </div>
      <p class="privacy-note">不会询问或保存姓名、身份证、银行卡、账号或精确住址。</p>
    `;
    fillFields(elements.onboardingContent, onboardingDraft);
  }

  function renderOnboardingSummary() {
    const completeness = model.calculateCompleteness(onboardingDraft);
    const missing = model.missingFields(onboardingDraft);
    const derived = model.calculateDerived(onboardingDraft);
    elements.onboardingContent.innerHTML = `
      <div class="onboarding-progress complete">
        <span>请确认画像</span><strong>${formatPercent(completeness)}</strong>
        <div><i style="width:${completeness * 100}%"></i></div>
      </div>
      <div class="onboarding-question">
        <span class="question-kicker">CONFIRM BEFORE SAVE</span>
        <h2>画像已整理，请确认后保存</h2>
        <p class="question-why">未填写项会保持为空，不会自动填成 0。以后可以在“用户画像”页面随时修改。</p>
        <div class="onboarding-summary-grid">
          ${summaryItem("投资目标", displayValue(onboardingDraft.investment_goal))}
          ${summaryItem("投资期限", formatMonths(onboardingDraft.investment_horizon_months))}
          ${summaryItem("每月结余", formatCurrency(derived.monthly_surplus_cny))}
          ${summaryItem("应急资金覆盖", formatMonthsValue(derived.emergency_fund_months))}
          ${summaryItem("可投资资金", formatCurrency(onboardingDraft.available_investment_funds_cny))}
          ${summaryItem("最大亏损边界", formatPercent(onboardingDraft.max_acceptable_loss_ratio))}
        </div>
        <div class="missing-summary">
          <strong>${missing.length ? `还有 ${missing.length} 项待补充` : "画像字段已完整"}</strong>
          <span>${missing.length ? missing.map((field) => FIELD_LABELS[field]).join("、") : "之后可随时更新"}</span>
        </div>
        <div class="profile-form-error" id="onboardingError" role="alert"></div>
      </div>
      <div class="onboarding-actions">
        <button type="button" class="ghost-button" data-onboarding="back">返回修改</button>
        <button type="button" class="primary-button" data-onboarding="confirm">确认并保存画像</button>
      </div>
      <p class="privacy-note">画像只保存在当前浏览器，并在任务请求时发送经后端重新验证的快照。</p>
    `;
  }

  function handleOnboardingClick(event) {
    const action = event.target.closest("[data-onboarding]")?.dataset.onboarding;
    if (action === "back") {
      onboardingStep = Math.max(0, onboardingStep - 1);
      renderOnboarding();
    } else if (action === "skip") {
      const step = STEPS[onboardingStep];
      (step.fields || [step.key]).forEach((field) => {
        onboardingDraft[field] = null;
      });
      onboardingStep += 1;
      renderOnboarding();
    } else if (action === "next") {
      if (applyOnboardingStep()) {
        onboardingStep += 1;
        renderOnboarding();
      }
    } else if (action === "confirm") {
      saveCompletedOnboarding();
    } else if (action === "add-position") {
      addPositionRow(elements.onboardingContent, "onboarding");
    } else if (action === "remove-position") {
      event.target.closest(".position-row")?.remove();
    } else if (action === "no-positions") {
      toggleNoPositions(elements.onboardingContent, event.target.checked);
    }
  }

  function applyOnboardingStep() {
    const step = STEPS[onboardingStep];
    try {
      const next = JSON.parse(JSON.stringify(onboardingDraft));
      readFields(elements.onboardingContent, next, step.fields || [step.key], "onboarding");
      assertValid(next);
      onboardingDraft = next;
      return true;
    } catch (error) {
      showFormError(elements.onboardingContent, error);
      return false;
    }
  }

  function saveCompletedOnboarding() {
    try {
      const saved = model.stampProfile(onboardingDraft, {
        previous: profile,
        onboardingCompleted: true,
      });
      model.saveProfile(saved, root.localStorage);
      profile = saved;
      closeOnboarding();
      renderProfileBadge();
      renderProfilePage();
      setPage("research");
      showToast("用户画像已确认并保存在当前浏览器。", "success");
    } catch (error) {
      showFormError(elements.onboardingContent, error);
    }
  }

  function renderProfileBadge() {
    if (!elements.profileCompletenessBadge) return;
    const completeness = profile ? model.calculateCompleteness(profile) : 0;
    elements.profileCompletenessBadge.textContent = profile
      ? `画像 ${formatPercent(completeness)}`
      : "画像未建立";
    elements.profileCompletenessBadge.classList.toggle(
      "incomplete",
      !profile || completeness < 1,
    );
  }

  function renderProfilePage() {
    if (!elements.profilePageContent) return;
    const current = profile || model.createEmptyProfile();
    const derived = model.calculateDerived(current);
    const missing = model.missingFields(current);
    elements.profilePageContent.innerHTML = `
      <div class="profile-hero-card">
        <div>
          <span class="section-number">USER PROFILE</span>
          <h1>用户画像</h1>
          <p>这里只保存你确认的财务事实和确定性计算，不生成综合风险等级或买卖建议。</p>
        </div>
        <div class="completeness-ring" style="--complete:${derived.profile_completeness * 360}deg">
          <strong>${formatPercent(derived.profile_completeness)}</strong><span>完整度</span>
        </div>
      </div>
      <div class="profile-missing ${missing.length ? "" : "complete"}">
        <strong>${missing.length ? "待补充项" : "画像字段已完整"}</strong>
        <span>${missing.length ? missing.map((field) => FIELD_LABELS[field]).join("、") : "没有缺失项"}</span>
      </div>
      <div class="derived-grid">
        ${metricCard("每月结余", formatCurrency(derived.monthly_surplus_cny), "收入 - 必要支出 - 债务还款")}
        ${metricCard("应急资金覆盖", formatMonthsValue(derived.emergency_fund_months), "应急资金 ÷ 每月必要支出")}
        ${metricCard("债务还款占收入", formatPercent(derived.debt_payment_ratio), "每月还款 ÷ 税后收入")}
        ${metricCard("已知持仓集中度", formatPercent(derived.known_asset_concentration), "已知的最大单项持仓占比")}
      </div>
      <div class="profile-sections">
        ${cashflowSection(current)}
        ${bufferSection(current)}
        ${fundsSection(current)}
        ${goalSection(current)}
        ${positionsSection(current)}
        ${experienceSection(current)}
      </div>
      <div class="profile-meta-card">
        <div><span>画像版本</span><strong>v${current.profile_version}</strong></div>
        <div><span>最近更新时间</span><strong>${formatDate(current.updated_at)}</strong></div>
        <div><span>保存位置</span><strong>当前浏览器 localStorage</strong></div>
      </div>
      <div class="danger-actions">
        <button type="button" class="ghost-button" data-profile-action="restart">重新进行画像建档</button>
        <button type="button" class="danger-button" data-profile-action="clear">清空用户画像</button>
      </div>
    `;
    fillFields(elements.profilePageContent, current);
  }

  function handleProfilePageClick(event) {
    const action = event.target.closest("[data-profile-action]")?.dataset.profileAction;
    if (action === "save-section") {
      saveProfileSection(event.target.closest(".profile-section"));
    } else if (action === "add-position") {
      addPositionRow(event.target.closest(".profile-section"), "profile");
    } else if (action === "remove-position") {
      event.target.closest(".position-row")?.remove();
    } else if (action === "no-positions") {
      toggleNoPositions(event.target.closest(".profile-section"), event.target.checked);
    } else if (action === "restart") {
      openOnboarding();
    } else if (action === "clear") {
      clearProfileWithConfirmation();
    }
  }

  function saveProfileSection(section) {
    if (!section) return;
    try {
      const next = JSON.parse(JSON.stringify(profile || model.createEmptyProfile()));
      const fields = section.dataset.fields.split(",");
      readFields(section, next, fields, "profile");
      const saved = model.stampProfile(next, {
        previous: profile,
        onboardingCompleted: true,
      });
      assertValid(saved);
      model.saveProfile(saved, root.localStorage);
      profile = saved;
      renderProfileBadge();
      renderProfilePage();
      showToast("本模块已保存，之后的任务将使用更新后的画像。", "success");
    } catch (error) {
      showFormError(section, error);
    }
  }

  function clearProfileWithConfirmation() {
    const confirmed = root.confirm(
      "确认清空用户画像？此操作会删除当前浏览器中的全部画像字段，并重新进入首次建档。",
    );
    if (!confirmed) return;
    model.clearProfile(root.localStorage);
    profile = null;
    renderProfileBadge();
    renderProfilePage();
    setPage("research");
    showToast("用户画像已从当前浏览器清空。", "success");
    openOnboarding();
  }

  function readFields(container, target, fields, scope) {
    fields.forEach((field) => {
      if (field === "existing_positions") {
        target[field] = readPositions(container, scope);
        return;
      }
      const input = container.querySelector(`[name="${field}"]`);
      if (!input) return;
      if (field === "investment_goal") {
        target[field] = input.value.trim() || null;
      } else if (field === "liquidity_need" || field === "investment_experience") {
        target[field] = input.value || null;
      } else if (field === "max_acceptable_loss_ratio") {
        target[field] = input.value === "" ? null : Number(input.value) / 100;
      } else {
        target[field] = input.value === "" ? null : Number(input.value);
      }
    });
  }

  function readPositions(container, scope) {
    if (container.querySelector(`[name="${scope}_no_positions"]`)?.checked) return [];
    const rows = [...container.querySelectorAll(".position-row")];
    if (!rows.length) return null;
    const positions = rows.map((row) => ({
      asset_name: row.querySelector('[name="position_asset_name"]').value.trim(),
      asset_type: row.querySelector('[name="position_asset_type"]').value.trim(),
      amount_cny: nullableNumber(row.querySelector('[name="position_amount_cny"]').value),
      portfolio_ratio: nullablePercent(
        row.querySelector('[name="position_portfolio_ratio"]').value,
      ),
    }));
    const allBlank = positions.every(
      (item) =>
        !item.asset_name &&
        !item.asset_type &&
        item.amount_cny === null &&
        item.portfolio_ratio === null,
    );
    return allBlank ? null : positions;
  }

  function assertValid(candidate) {
    const validation = model.validateProfile(candidate);
    if (!validation.valid) {
      const error = new Error(Object.values(validation.errors)[0]);
      error.validationErrors = validation.errors;
      throw error;
    }
  }

  function fillFields(container, source) {
    container.querySelectorAll("[name]").forEach((input) => {
      const field = input.name;
      if (!(field in source) || source[field] === null) return;
      input.value =
        field === "max_acceptable_loss_ratio"
          ? source[field] * 100
          : source[field];
    });
    const positions = source.existing_positions;
    if (Array.isArray(positions) && positions.length) {
      const list = container.querySelector(".positions-list");
      if (list) {
        list.innerHTML = positions
          .map((position) => positionRowMarkup(position))
          .join("");
      }
    }
    const scope = container.querySelector("[data-position-scope]")?.dataset.positionScope;
    if (scope && Array.isArray(positions) && positions.length === 0) {
      const checkbox = container.querySelector(`[name="${scope}_no_positions"]`);
      if (checkbox) {
        checkbox.checked = true;
        toggleNoPositions(container, true);
      }
    }
  }

  function showFormError(container, error) {
    const target = container.querySelector(".profile-form-error");
    if (target) target.textContent = error instanceof Error ? error.message : "输入无效";
  }

  function showToast(message, type) {
    if (!elements.profileToast) return;
    elements.profileToast.textContent = message;
    elements.profileToast.className = `profile-toast ${type}`;
    elements.profileToast.hidden = false;
    root.setTimeout(() => {
      elements.profileToast.hidden = true;
    }, 4200);
  }

  function addPositionRow(container) {
    const list = container.querySelector(".positions-list");
    if (!list) return;
    list.insertAdjacentHTML("beforeend", positionRowMarkup());
  }

  function toggleNoPositions(container, checked) {
    const editor = container.querySelector(".positions-editor");
    if (editor) editor.hidden = checked;
  }

  function cashflowSection(current) {
    return sectionMarkup(
      "每月收支",
      [
        "monthly_after_tax_income_cny",
        "monthly_essential_expenses_cny",
        "monthly_debt_payment_cny",
      ],
      `${moneyMarkup("monthly_after_tax_income_cny", "每月税后收入")}
       ${moneyMarkup("monthly_essential_expenses_cny", "每月必要支出")}
       ${moneyMarkup("monthly_debt_payment_cny", "每月债务还款")}`,
      current,
    );
  }

  function bufferSection(current) {
    return sectionMarkup(
      "财务缓冲",
      [
        "emergency_fund_cny",
        "planned_large_expenses_cny",
        "planned_large_expenses_within_months",
      ],
      `${moneyMarkup("emergency_fund_cny", "应急资金")}
       ${moneyMarkup("planned_large_expenses_cny", "计划大额支出")}
       ${numberMarkup("planned_large_expenses_within_months", "预计几个月内发生", 0, 1200)}`,
      current,
    );
  }

  function fundsSection(current) {
    return sectionMarkup(
      "投资资金与亏损边界",
      ["available_investment_funds_cny", "max_acceptable_loss_ratio"],
      `${moneyMarkup("available_investment_funds_cny", "可投资资金")}
       ${percentMarkup("max_acceptable_loss_ratio", "最大可接受亏损")}`,
      current,
      "最大亏损只表示你明确表达的边界，不代表系统建议承担该亏损。",
    );
  }

  function goalSection(current) {
    return sectionMarkup(
      "投资目标、期限与流动性",
      ["investment_goal", "investment_horizon_months", "liquidity_need"],
      `${fieldMarkup("investment_goal", "textarea", { label: "投资目标" })}
       ${numberMarkup("investment_horizon_months", "投资期限（月）", 1, 1200)}
       ${selectMarkup("liquidity_need", "流动性需求", LIQUIDITY_LABELS)}`,
      current,
    );
  }

  function positionsSection(current) {
    return sectionMarkup(
      "当前持仓",
      ["existing_positions"],
      positionsMarkup(current.existing_positions, "profile"),
      current,
      "明确没有持仓会保存为空列表；尚未回答会保持为空值。",
    );
  }

  function experienceSection(current) {
    return sectionMarkup(
      "投资经验",
      ["investment_experience"],
      selectMarkup("investment_experience", "实际投资经验", EXPERIENCE_LABELS),
      current,
      "投资经验不会被单独用来判断你适合承担更高风险。",
    );
  }

  function sectionMarkup(title, fields, controls, current, help = "") {
    const wrapper = document.createElement("div");
    wrapper.innerHTML = controls;
    fillFields(wrapper, current);
    return `
      <section class="profile-section" data-fields="${fields.join(",")}">
        <div class="profile-section-heading">
          <div><h2>${title}</h2>${help ? `<p>${help}</p>` : ""}</div>
          <button type="button" class="section-save-button" data-profile-action="save-section">保存本模块</button>
        </div>
        <div class="profile-field-grid">${wrapper.innerHTML}</div>
        <div class="profile-form-error" role="alert"></div>
      </section>
    `;
  }

  function fieldMarkup(name, type, options = {}) {
    const label = options.label || FIELD_LABELS[name];
    if (type === "textarea") {
      return `<label class="profile-field"><span>${label}</span>
        <textarea name="${name}" rows="3" maxlength="500" placeholder="${options.placeholder || ""}"></textarea>
      </label>`;
    }
    return `<label class="profile-field"><span>${label}</span>
      <input name="${name}" type="${type}" />
    </label>`;
  }

  function moneyMarkup(name, label = FIELD_LABELS[name]) {
    return `<label class="profile-field"><span>${label}</span>
      <div class="input-with-unit"><span>¥</span><input name="${name}" type="number" min="0" max="1000000000000" step="1" inputmode="numeric" placeholder="可填写大致整数金额" /></div>
    </label>`;
  }

  function numberMarkup(name, label, min, max) {
    return `<label class="profile-field"><span>${label}</span>
      <input name="${name}" type="number" min="${min}" max="${max}" step="1" inputmode="numeric" />
    </label>`;
  }

  function percentMarkup(name, label = "最大可接受亏损") {
    return `<label class="profile-field"><span>${label}</span>
      <div class="input-with-unit suffix"><input name="${name}" type="number" min="0" max="100" step="0.1" inputmode="decimal" placeholder="例如 10" /><span>%</span></div>
    </label>`;
  }

  function selectMarkup(name, label, options) {
    return `<label class="profile-field"><span>${label}</span>
      <select name="${name}"><option value="">暂时不确定</option>${Object.entries(options)
        .map(([value, text]) => `<option value="${value}">${text}</option>`)
        .join("")}</select>
    </label>`;
  }

  function positionsMarkup(positions, scope) {
    const items = Array.isArray(positions) && positions.length ? positions : [null];
    return `<div class="positions-block" data-position-scope="${scope}">
      <label class="no-positions-check">
        <input type="checkbox" name="${scope}_no_positions" data-${
          scope === "profile" ? "profile-action" : "onboarding"
        }="no-positions" />
        我明确没有投资持仓
      </label>
      <div class="positions-editor">
        <div class="positions-list">${items.map(positionRowMarkup).join("")}</div>
        <button type="button" class="ghost-button compact" data-${
          scope === "profile" ? "profile-action" : "onboarding"
        }="add-position">＋ 添加一项持仓</button>
      </div>
    </div>`;
  }

  function positionRowMarkup(position = null) {
    const item = position || {
      asset_name: "",
      asset_type: "",
      amount_cny: null,
      portfolio_ratio: null,
    };
    return `<div class="position-row">
      <label><span>资产名称</span><input name="position_asset_name" maxlength="100" value="${escapeHtml(item.asset_name || "")}" placeholder="例如：沪深300指数基金" /></label>
      <label><span>资产类型</span><input name="position_asset_type" maxlength="50" value="${escapeHtml(item.asset_type || "")}" placeholder="基金、股票、存款等" /></label>
      <label><span>大致金额（元）</span><input name="position_amount_cny" type="number" min="0" max="1000000000000" step="1" value="${item.amount_cny ?? ""}" /></label>
      <label><span>占投资资产（%）</span><input name="position_portfolio_ratio" type="number" min="0" max="100" step="0.1" value="${item.portfolio_ratio === null ? "" : item.portfolio_ratio * 100}" /></label>
      <button type="button" class="remove-position" data-profile-action="remove-position" data-onboarding="remove-position" aria-label="删除这项持仓">×</button>
    </div>`;
  }

  function metricCard(label, value, note) {
    return `<div class="derived-card"><span>${label}</span><strong>${value}</strong><small>${note}</small></div>`;
  }

  function summaryItem(label, value) {
    return `<div><span>${label}</span><strong>${value}</strong></div>`;
  }

  function nullableNumber(value) {
    return value === "" ? null : Number(value);
  }

  function nullablePercent(value) {
    return value === "" ? null : Number(value) / 100;
  }

  function formatCurrency(value) {
    if (value === null || value === undefined) return "未填写";
    return new Intl.NumberFormat("zh-CN", {
      style: "currency",
      currency: "CNY",
      maximumFractionDigits: 0,
    }).format(value);
  }

  function formatPercent(value) {
    if (value === null || value === undefined) return "未填写";
    return `${(value * 100).toFixed(value * 100 % 1 ? 1 : 0)}%`;
  }

  function formatMonths(value) {
    return value === null || value === undefined ? "未填写" : `${value} 个月`;
  }

  function formatMonthsValue(value) {
    return value === null || value === undefined ? "未填写" : `${value.toFixed(1)} 个月`;
  }

  function formatDate(value) {
    if (!value) return "尚未保存";
    return new Intl.DateTimeFormat("zh-CN", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  }

  function displayValue(value) {
    return value === null || value === undefined || value === "" ? "未填写" : escapeHtml(String(value));
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  root.AlphaOSProfileUI = { init, getProfile, openProfile: () => setPage("profile") };
})(typeof globalThis !== "undefined" ? globalThis : this);
