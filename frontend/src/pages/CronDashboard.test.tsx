import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ChatSandboxSpendStatus } from "@/lib/api";
import { ChatComputePanel } from "./CronDashboard";

const status = (overrides: Partial<ChatSandboxSpendStatus> = {}): ChatSandboxSpendStatus => ({
  environment: "staging",
  billing_cycle: "2026-08-01",
  cycle_end_at: "2026-09-01T00:00:00Z",
  circuit_state: "armed",
  trip_reason: null,
  tripped_at: null,
  estimated_microusd: 10_000_000,
  provider_floor_microusd: 9_000_000,
  effective_microusd: 10_000_000,
  warning_microusd: 75_000_000,
  application_cap_microusd: 100_000_000,
  environment_cap_microusd: 125_000_000,
  workspace_cap_microusd: 250_000_000,
  remaining_microusd: 90_000_000,
  reconciliation_state: "fresh",
  last_metered_at: "2026-08-03T12:00:00Z",
  last_reconciled_at: "2026-08-03T12:00:00Z",
  last_reconciliation_attempt_at: "2026-08-03T12:00:00Z",
  next_reconciliation_at: "2026-08-03T13:00:00Z",
  live_count: 1,
  termination_uncertain_count: 0,
  live_states: { starting: 0, blank: 1, busy: 0, idle: 0, draining: 0, termination_uncertain: 0 },
  burn_rate_microusd_per_hour: null,
  projected_cap_hit_at: null,
  prior_cycle: null,
  daily_spend: [{ date: "2026-08-03", blank_pool_microusd: 1_000_000, assigned_microusd: 9_000_000 }],
  events: [],
  ...overrides,
});

describe("ChatComputePanel", () => {
  it.each([
    ["fresh", status(), "Fresh"],
    ["stale", status({ reconciliation_state: "stale" }), "Stale"],
    ["warning", status({ circuit_state: "warning" }), "Operator warning"],
    ["tripped", status({ circuit_state: "tripped", trip_reason: "application_cap" }), "Chat disabled"],
    ["empty", status({ live_count: 0, daily_spend: [] }), "No compute recorded in this cycle."],
    ["unavailable", status({ reconciliation_state: "unavailable", last_reconciled_at: null, next_reconciliation_at: null }), "Unavailable"],
  ])("renders %s state", (_name, data, expected) => {
    render(<ChatComputePanel data={data as ChatSandboxSpendStatus} loading={false} error={null} />);
    expect(screen.getAllByText(expected as string).length).toBeGreaterThan(0);
  });
});
