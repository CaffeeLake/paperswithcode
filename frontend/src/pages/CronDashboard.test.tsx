import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CronJobCard } from "@/components/cron/CronJobCard";
import type { ChatSandboxSpendStatus } from "@/lib/api/chat";
import { operationsApi, type CronJobsResponse, type CronJobStatus, type PaperMarkdownJobsResponse } from "@/lib/api/operations";
import {
  ChatComputePanel,
  CronSnapshotNotice,
  cronStatusRefetchInterval,
} from "./CronDashboard";

afterEach(() => {
  vi.unstubAllGlobals();
});

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

  it("explains paper Markdown spend, reservations, and rolling window", () => {
    const budget = {
      mode: "live" as const,
      window: "rolling_30_days" as const,
      window_days: 30,
      window_started_at: "2026-07-18T12:00:00Z",
      next_release_at: "2026-08-20T12:00:00Z",
      next_release_usd: 4.5,
      spent_usd: 86.73,
      active_reserved_usd: 0,
      desired_jobs: 1,
      affordable_jobs: 0,
      planned_jobs: 0,
      planned_reserved_usd: 0,
      current_exposure_usd: 86.73,
      projected_usd: 86.73,
      ceiling_usd: 100,
      headroom_usd: 13.27,
      can_launch_planned: false,
      hourly_rate_usd: 1.8,
      reservation_hours_per_job: 12,
      reservation_per_job_usd: 21.6,
      relevant_jobs: 5,
    };
    const monitor: PaperMarkdownJobsResponse = {
      available: true,
      namespace: "huggingface",
      jobs: [],
      summary: {},
      budgets: {
        live: budget,
        backfill: {
          ...budget,
          mode: "backfill",
          window: "all_history",
          window_days: null,
          next_release_at: null,
          next_release_usd: 0,
          ceiling_usd: 750,
          desired_jobs: 4,
          affordable_jobs: 3,
          planned_jobs: 3,
          planned_reserved_usd: 64.8,
          projected_usd: 151.53,
          can_launch_planned: true,
        },
      },
    };

    render(
      <CronJobCard
        job={{ ...job, job_name: "paper_markdown_backfill" }}
        expanded
        onToggle={() => undefined}
        paperMarkdownJobs={monitor}
      />,
    );

    expect(screen.getByText("Rolling 30-day window")).toBeInTheDocument();
    expect(screen.getByText("No shard fits")).toBeInTheDocument();
    expect(screen.getByText("3 of 4 planned shards fit")).toBeInTheDocument();
    expect(screen.getByText("Live GPU budget:").parentElement).toHaveTextContent("$86.73 current / $100.00 cap · 0 of 1 planned · projects $86.73");
    expect(screen.getByText("All history · no automatic reset")).toBeInTheDocument();
    expect(screen.getAllByText(/not a provider invoice/i)).toHaveLength(2);
  });
});

describe("CronSnapshotNotice", () => {
  const snapshot = (overrides: Partial<CronJobsResponse> = {}): CronJobsResponse => ({
    timestamp: "2026-08-14T12:00:00Z",
    jobs: [],
    manual_operations: [],
    summary: {
      total_jobs: 0,
      healthy: 0,
      degraded: 0,
      broken: 0,
      running: 0,
      stuck: 0,
      unknown: 0,
      health_score: 100,
      critical_issues: [],
      what_to_check_next: "All monitored jobs look healthy",
      coverage: {
        registered_scheduled_duties: 0,
        discovered_scheduled_duties: 0,
        monitored_duties: 0,
        coverage_gaps: 0,
        gap_ids: [],
      },
    },
    snapshot_generated_at: "2026-08-14T11:58:59Z",
    snapshot_age_seconds: 61,
    snapshot_stale: true,
    refreshing: true,
    ...overrides,
  });

  it("shows stale data while a refresh runs", () => {
    render(<CronSnapshotNotice data={snapshot()} />);
    expect(screen.getByRole("status")).toHaveTextContent("61 seconds old");
  });

  it("stays hidden for a fresh snapshot", () => {
    render(<CronSnapshotNotice data={snapshot({ snapshot_stale: false })} />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("polls quickly until the replacement snapshot is fresh", () => {
    expect(cronStatusRefetchInterval(snapshot(), false)).toBe(1000);
    expect(
      cronStatusRefetchInterval(
        snapshot({ snapshot_stale: false, refreshing: false }),
        true,
      ),
    ).toBe(30000);
    expect(
      cronStatusRefetchInterval(
        snapshot({ snapshot_stale: false, refreshing: false }),
        false,
      ),
    ).toBe(false);
  });

  it("uses the forced endpoint for a manual status refresh", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(snapshot()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await operationsApi.getCronStatus(true);

    expect(String(fetchMock.mock.calls[0][0])).toContain(
      "/cron/status?force_refresh=true",
    );
  });
});
