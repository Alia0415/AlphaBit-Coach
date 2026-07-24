"use strict";

const assert = require("node:assert/strict");
const profileModel = require("../frontend/user-profile.js");

function storageMock() {
  const values = new Map();
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
    removeItem(key) {
      values.delete(key);
    },
  };
}

function completedProfile(overrides = {}) {
  return {
    ...profileModel.createEmptyProfile(),
    investment_goal: "五年后购房准备",
    investment_horizon_months: 60,
    liquidity_need: "medium",
    monthly_after_tax_income_cny: 20000,
    monthly_essential_expenses_cny: 8000,
    monthly_debt_payment_cny: 2000,
    emergency_fund_cny: 48000,
    planned_large_expenses_cny: 30000,
    planned_large_expenses_within_months: 10,
    available_investment_funds_cny: 100000,
    max_acceptable_loss_ratio: 0.1,
    investment_experience: "basic",
    existing_positions: [],
    onboarding_completed: true,
    profile_version: 1,
    created_at: "2026-07-24T08:00:00.000Z",
    updated_at: "2026-07-24T08:00:00.000Z",
    ...overrides,
  };
}

{
  assert.equal(profileModel.shouldStartOnboarding(null), true);
  assert.equal(
    profileModel.shouldStartOnboarding(profileModel.createEmptyProfile()),
    true,
  );
  assert.equal(profileModel.shouldStartOnboarding(completedProfile()), false);
}

{
  const storage = storageMock();
  const profile = completedProfile();
  profileModel.saveProfile(profile, storage);
  const refreshed = profileModel.loadProfile(storage);
  assert.deepEqual(refreshed.profile, profile);
  assert.equal(refreshed.reset, false);

  const changed = profileModel.stampProfile(
    { ...refreshed.profile, investment_goal: "退休储备" },
    {
      previous: refreshed.profile,
      now: "2026-07-24T09:00:00.000Z",
      onboardingCompleted: true,
    },
  );
  profileModel.saveProfile(changed, storage);
  assert.equal(profileModel.loadProfile(storage).profile.investment_goal, "退休储备");
  assert.equal(changed.profile_version, 2);
  assert.equal(changed.updated_at, "2026-07-24T09:00:00.000Z");

  profileModel.clearProfile(storage);
  assert.equal(profileModel.loadProfile(storage).profile, null);
}

{
  const derived = profileModel.calculateDerived(completedProfile());
  assert.equal(derived.monthly_surplus_cny, 10000);
  assert.equal(derived.emergency_fund_months, 6);
  assert.equal(derived.debt_payment_ratio, 0.1);
  assert.equal(derived.known_asset_concentration, 0);
  assert.equal(derived.profile_completeness, 1);
}

{
  const empty = profileModel.createEmptyProfile();
  assert.equal(empty.monthly_after_tax_income_cny, null);
  assert.equal(empty.existing_positions, null);
  assert.equal(profileModel.calculateDerived(empty).monthly_surplus_cny, null);

  const explicitNoPositions = { ...empty, existing_positions: [] };
  assert.equal(
    profileModel.calculateDerived(explicitNoPositions).known_asset_concentration,
    0,
  );
  assert.equal(profileModel.calculateDerived(empty).known_asset_concentration, null);
}

{
  assert.equal(
    profileModel.validateProfile(
      completedProfile({ max_acceptable_loss_ratio: 1.01 }),
    ).valid,
    false,
  );
  assert.equal(
    profileModel.validateProfile(
      completedProfile({ monthly_after_tax_income_cny: -1 }),
    ).valid,
    false,
  );
  assert.equal(
    profileModel.validateProfile(
      completedProfile({ monthly_after_tax_income_cny: 1.5 }),
    ).valid,
    false,
  );
}

{
  const storage = storageMock();
  storage.setItem(profileModel.PROFILE_STORAGE_KEY, "{not-json");
  const invalidJson = profileModel.loadProfile(storage);
  assert.equal(invalidJson.profile, null);
  assert.equal(invalidJson.reset, true);
  assert.equal(storage.getItem(profileModel.PROFILE_STORAGE_KEY), null);

  storage.setItem(
    profileModel.PROFILE_STORAGE_KEY,
    JSON.stringify(completedProfile({ bank_card_number: "secret" })),
  );
  const sensitive = profileModel.loadProfile(storage);
  assert.equal(sensitive.profile, null);
  assert.equal(sensitive.reset, true);
}

console.log("user profile frontend tests passed");
