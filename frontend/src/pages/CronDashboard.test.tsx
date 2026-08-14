import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CronJobCard } from "@/components/cron/CronJobCard";
import type { ChatSandboxSpendStatus, CronJobStatus } from "@/lib/api";
import { ChatComputePanel } from "./CronDashboard";

const status = (overrides: Partial<ChatSandboxSpendStatus> = {}): ChatSandboxSpendStatus => ({
  environment: "staging",
  provider_mode: "starter_workspace",
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
  environment_cap_microusd: null,
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

describe("CronJobCard health axes", () => {
  const job: CronJobStatus = {
    job_name: "example",
    display_name: "Example scheduled job",
    category: "hourly",
    dashboard_group: "operations",
    status: "broken",
    status_reason: "Execution: scheduled workflow failed; Output: fresh output",
    last_run: "2026-08-14T12:00:00Z",
    last_db_write: "2026-08-14T12:01:00Z",
    recent_write_count: 10,
    duration: 30,
    is_running: false,
    error: null,
    schedule: "0 * * * *",
    critical: true,
    execution_health: {
      status: "broken",
      reason: "scheduled workflow failed",
      scheduler: "github_actions",
      last_expected_at: "2026-08-14T12:00:00Z",
      last_started_at: "2026-08-14T12:00:30Z",
      last_completed_at: "2026-08-14T12:01:00Z",
      next_expected_at: "2026-08-14T13:00:00Z",
    },
    output_health: {
      status: "healthy",
      reason: "fresh output",
      last_verified_at: "2026-08-14T12:01:00Z",
    },
    diagnostic_groups: {
      scheduler_orchestration: ["scheduled workflow failed"],
      credential_provider: [],
    },
  };

  it("renders axes independently and exposes scheduler evidence", () => {
    const { rerender } = render(
      <CronJobCard job={job} expanded={false} onToggle={() => undefined} />,
    );
    expect(screen.getByText("Execution: broken")).toBeInTheDocument();
    expect(screen.getByText("Output: healthy")).toBeInTheDocument();
    expect(screen.getByText("broken")).toBeInTheDocument();

    rerender(<CronJobCard job={job} expanded={true} onToggle={() => undefined} />);
    expect(screen.getByText("Scheduler evidence")).toBeInTheDocument();
    expect(screen.getByText("github_actions")).toBeInTheDocument();
    rerender(<CronJobCard job={{ ...job, recent_write_count: 11 }} expanded={true} onToggle={() => undefined} />);
    expect(screen.getByText("Scheduler evidence")).toBeInTheDocument();
  });
});
