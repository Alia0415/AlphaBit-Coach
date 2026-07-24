(function attachUserProfileModel(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.AlphaOSUserProfile = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function createModel() {
  "use strict";

  const PROFILE_STORAGE_KEY = "alphaos_user_profile";
  const MAX_CNY_AMOUNT = 1_000_000_000_000;
  const PROFILE_FACT_FIELDS = [
    "investment_goal",
    "investment_horizon_months",
    "liquidity_need",
    "monthly_after_tax_income_cny",
    "monthly_essential_expenses_cny",
    "monthly_debt_payment_cny",
    "emergency_fund_cny",
    "planned_large_expenses_cny",
    "planned_large_expenses_within_months",
    "available_investment_funds_cny",
    "max_acceptable_loss_ratio",
    "investment_experience",
    "existing_positions",
  ];
  const STATE_FIELDS = [
    "onboarding_completed",
    "profile_version",
    "created_at",
    "updated_at",
  ];
  const ALLOWED_FIELDS = new Set([...PROFILE_FACT_FIELDS, ...STATE_FIELDS]);
  const POSITION_FIELDS = new Set([
    "asset_name",
    "asset_type",
    "amount_cny",
    "portfolio_ratio",
  ]);

  function createEmptyProfile() {
    return {
      investment_goal: null,
      investment_horizon_months: null,
      liquidity_need: null,
      monthly_after_tax_income_cny: null,
      monthly_essential_expenses_cny: null,
      monthly_debt_payment_cny: null,
      emergency_fund_cny: null,
      planned_large_expenses_cny: null,
      planned_large_expenses_within_months: null,
      available_investment_funds_cny: null,
      max_acceptable_loss_ratio: null,
      investment_experience: null,
      existing_positions: null,
      onboarding_completed: false,
      profile_version: 1,
      created_at: null,
      updated_at: null,
    };
  }

  function validateProfile(profile) {
    const errors = {};
    if (!isPlainObject(profile)) {
      return { valid: false, errors: { profile: "画像数据必须是对象" } };
    }
    const unknown = Object.keys(profile).filter((key) => !ALLOWED_FIELDS.has(key));
    if (unknown.length) {
      errors.profile = `包含不允许保存的字段：${unknown.join("、")}`;
    }
    validateOptionalText(profile.investment_goal, "investment_goal", 500, errors);
    validateOptionalInteger(
      profile.investment_horizon_months,
      "investment_horizon_months",
      1,
      1200,
      errors,
    );
    validateEnum(
      profile.liquidity_need,
      "liquidity_need",
      ["high", "medium", "low"],
      errors,
    );
    [
      "monthly_after_tax_income_cny",
      "monthly_essential_expenses_cny",
      "monthly_debt_payment_cny",
      "emergency_fund_cny",
      "planned_large_expenses_cny",
      "available_investment_funds_cny",
    ].forEach((field) => {
      validateOptionalInteger(profile[field], field, 0, MAX_CNY_AMOUNT, errors);
    });
    validateOptionalInteger(
      profile.planned_large_expenses_within_months,
      "planned_large_expenses_within_months",
      0,
      1200,
      errors,
    );
    validateOptionalRatio(
      profile.max_acceptable_loss_ratio,
      "max_acceptable_loss_ratio",
      errors,
    );
    validateEnum(
      profile.investment_experience,
      "investment_experience",
      ["none", "basic", "experienced"],
      errors,
    );
    validatePositions(profile.existing_positions, errors);

    if (typeof profile.onboarding_completed !== "boolean") {
      errors.onboarding_completed = "建档状态必须为 true 或 false";
    }
    if (!Number.isInteger(profile.profile_version) || profile.profile_version < 1) {
      errors.profile_version = "画像版本必须是大于等于 1 的整数";
    }
    validateTimestamp(profile.created_at, "created_at", errors);
    validateTimestamp(profile.updated_at, "updated_at", errors);
    if (
      profile.onboarding_completed &&
      (!profile.created_at || !profile.updated_at)
    ) {
      errors.updated_at = "完成建档前必须记录创建和更新时间";
    }
    if (
      profile.created_at &&
      profile.updated_at &&
      Date.parse(profile.updated_at) < Date.parse(profile.created_at)
    ) {
      errors.updated_at = "更新时间不能早于创建时间";
    }
    return { valid: Object.keys(errors).length === 0, errors };
  }

  function validatePositions(positions, errors) {
    if (positions === null) return;
    if (!Array.isArray(positions)) {
      errors.existing_positions = "当前持仓必须是列表、空列表或未填写";
      return;
    }
    if (positions.length > 100) {
      errors.existing_positions = "持仓最多填写 100 项";
      return;
    }
    positions.forEach((position, index) => {
      const prefix = `existing_positions.${index}`;
      if (!isPlainObject(position)) {
        errors[prefix] = `第 ${index + 1} 项持仓格式不正确`;
        return;
      }
      const unknown = Object.keys(position).filter(
        (key) => !POSITION_FIELDS.has(key),
      );
      if (unknown.length) {
        errors[prefix] = `第 ${index + 1} 项持仓包含不允许的字段`;
      }
      if (
        typeof position.asset_name !== "string" ||
        !position.asset_name.trim() ||
        position.asset_name.trim().length > 100
      ) {
        errors[`${prefix}.asset_name`] = `第 ${index + 1} 项持仓名称不能为空`;
      }
      if (
        typeof position.asset_type !== "string" ||
        !position.asset_type.trim() ||
        position.asset_type.trim().length > 50
      ) {
        errors[`${prefix}.asset_type`] = `第 ${index + 1} 项持仓类型不能为空`;
      }
      validateOptionalInteger(
        position.amount_cny,
        `${prefix}.amount_cny`,
        0,
        MAX_CNY_AMOUNT,
        errors,
      );
      validateOptionalRatio(
        position.portfolio_ratio,
        `${prefix}.portfolio_ratio`,
        errors,
      );
      if (position.amount_cny === null && position.portfolio_ratio === null) {
        errors[prefix] = `第 ${index + 1} 项持仓至少填写大致金额或占比`;
      }
    });
  }

  function validateOptionalText(value, field, maxLength, errors) {
    if (value === null) return;
    if (typeof value !== "string" || value.trim().length > maxLength) {
      errors[field] = `内容不能超过 ${maxLength} 个字符`;
    }
  }

  function validateOptionalInteger(value, field, min, max, errors) {
    if (value === null) return;
    if (!Number.isInteger(value) || value < min || value > max) {
      errors[field] = `请输入 ${min} 到 ${max} 之间的整数`;
    }
  }

  function validateOptionalRatio(value, field, errors) {
    if (value === null) return;
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1) {
      errors[field] = "比例必须在 0% 到 100% 之间";
    }
  }

  function validateEnum(value, field, allowed, errors) {
    if (value !== null && !allowed.includes(value)) {
      errors[field] = "选项不在允许范围内";
    }
  }

  function validateTimestamp(value, field, errors) {
    if (value === null) return;
    if (typeof value !== "string" || Number.isNaN(Date.parse(value))) {
      errors[field] = "时间格式无效";
    }
  }

  function calculateDerived(profile) {
    const allCashflowKnown = [
      profile.monthly_after_tax_income_cny,
      profile.monthly_essential_expenses_cny,
      profile.monthly_debt_payment_cny,
    ].every((value) => value !== null);
    const monthlySurplus = allCashflowKnown
      ? profile.monthly_after_tax_income_cny -
        profile.monthly_essential_expenses_cny -
        profile.monthly_debt_payment_cny
      : null;
    const emergencyMonths =
      profile.emergency_fund_cny !== null &&
      profile.monthly_essential_expenses_cny !== null &&
      profile.monthly_essential_expenses_cny !== 0
        ? profile.emergency_fund_cny / profile.monthly_essential_expenses_cny
        : null;
    const debtRatio =
      profile.monthly_debt_payment_cny !== null &&
      profile.monthly_after_tax_income_cny !== null &&
      profile.monthly_after_tax_income_cny !== 0
        ? profile.monthly_debt_payment_cny /
          profile.monthly_after_tax_income_cny
        : null;
    return {
      monthly_surplus_cny: monthlySurplus,
      emergency_fund_months: emergencyMonths,
      debt_payment_ratio: debtRatio,
      known_asset_concentration: calculateConcentration(
        profile.existing_positions,
      ),
      profile_completeness: calculateCompleteness(profile),
    };
  }

  function calculateConcentration(positions) {
    if (positions === null) return null;
    if (!positions.length) return 0;
    const ratios = positions
      .map((item) => item.portfolio_ratio)
      .filter((value) => value !== null);
    if (ratios.length) return Math.max(...ratios);
    if (positions.some((item) => item.amount_cny === null)) return null;
    const total = positions.reduce((sum, item) => sum + item.amount_cny, 0);
    if (total === 0) return null;
    return Math.max(...positions.map((item) => item.amount_cny / total));
  }

  function calculateCompleteness(profile) {
    const answered = PROFILE_FACT_FIELDS.filter(
      (field) => profile[field] !== null,
    ).length;
    return answered / PROFILE_FACT_FIELDS.length;
  }

  function missingFields(profile) {
    return PROFILE_FACT_FIELDS.filter((field) => profile[field] === null);
  }

  function stampProfile(profile, options = {}) {
    const now = options.now || new Date().toISOString();
    const previous = options.previous || null;
    return {
      ...profile,
      onboarding_completed:
        options.onboardingCompleted === undefined
          ? true
          : Boolean(options.onboardingCompleted),
      profile_version: previous
        ? Math.max(1, previous.profile_version + 1)
        : Math.max(1, profile.profile_version || 1),
      created_at: previous?.created_at || profile.created_at || now,
      updated_at: now,
    };
  }

  function loadProfile(storage) {
    const target = storage || globalThis.localStorage;
    const raw = target.getItem(PROFILE_STORAGE_KEY);
    if (raw === null) return { profile: null, reset: false, error: null };
    try {
      const profile = JSON.parse(raw);
      const validation = validateProfile(profile);
      if (!validation.valid) {
        target.removeItem(PROFILE_STORAGE_KEY);
        return {
          profile: null,
          reset: true,
          error: Object.values(validation.errors)[0],
        };
      }
      return { profile, reset: false, error: null };
    } catch (_error) {
      target.removeItem(PROFILE_STORAGE_KEY);
      return {
        profile: null,
        reset: true,
        error: "本地画像数据无法解析，已安全重置",
      };
    }
  }

  function saveProfile(profile, storage) {
    const validation = validateProfile(profile);
    if (!validation.valid) {
      const error = new Error(Object.values(validation.errors)[0]);
      error.validationErrors = validation.errors;
      throw error;
    }
    const target = storage || globalThis.localStorage;
    target.setItem(PROFILE_STORAGE_KEY, JSON.stringify(profile));
    return profile;
  }

  function clearProfile(storage) {
    const target = storage || globalThis.localStorage;
    target.removeItem(PROFILE_STORAGE_KEY);
  }

  function shouldStartOnboarding(profile) {
    return !profile || profile.onboarding_completed !== true;
  }

  function isPlainObject(value) {
    return (
      value !== null &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      Object.getPrototypeOf(value) === Object.prototype
    );
  }

  return {
    PROFILE_STORAGE_KEY,
    PROFILE_FACT_FIELDS,
    createEmptyProfile,
    validateProfile,
    calculateDerived,
    calculateCompleteness,
    missingFields,
    stampProfile,
    loadProfile,
    saveProfile,
    clearProfile,
    shouldStartOnboarding,
  };
});
