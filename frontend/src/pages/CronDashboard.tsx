import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Clock,
  XCircle,
  Loader2,
  Activity,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";
import { CronJobCard } from "@/components/cron/CronJobCard";
import { CodexJobQueue } from "@/components/admin/CodexJobQueue";
import { CatalogAuditPanel } from "@/components/admin/CatalogAuditPanel";
import { apiClient } from "@/lib/api";
import type { ChatSandboxSpendStatus, CronJobHealth, CronJobStatus } from "@/lib/api";
import { formatCronDate } from "@/lib/cronStatus";
import { useAuth } from "@/lib/authContext";
import "./CronDashboard.css";

const categoryColors: Record<string, string> = {
  hourly: "cron-status--running",
  daily: "cron-status--healthy",
  weekly: "cron-status--degraded",
};

const usd = (microusd: number) => `$${(microusd / 1_000_000).toFixed(2)}`;

export const ChatComputePanel = ({ data, loading, error }: {
  data?: ChatSandboxSpendStatus;
  loading: boolean;
  error: unknown;
}) => {
  if (loading) {
    return <div className="flex items-center py-12"><Loader2 className="h-6 w-6 animate-spin mr-3" />Loading chat compute…</div>;
  }
  if (error || !data) {
    return <Card className="cron-status--broken"><CardContent className="pt-6">Chat compute accounting is unavailable.</CardContent></Card>;
  }
  const percent = Math.min(100, data.effective_microusd / data.application_cap_microusd * 100);
  const stateLabel = data.circuit_state === "tripped" ? "Chat disabled" : data.circuit_state === "warning" ? "Operator warning" : "Enabled";
  const reconciliationLabel = data.reconciliation_state === "fresh" ? "Fresh" : data.reconciliation_state === "stale" ? "Stale" : "Unavailable";
  return <div className="space-y-6">
    <div className="grid md:grid-cols-4 gap-4">
      <Card className={data.circuit_state === "tripped" ? "cron-status--broken" : data.circuit_state === "warning" ? "cron-status--degraded" : ""}><CardHeader><CardTitle className="text-sm">Circuit</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{stateLabel}</div><p className="text-xs cron-muted">{data.trip_reason ?? "Policy armed"}</p></CardContent></Card>
      <Card><CardHeader><CardTitle className="text-sm">Month to date</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{usd(data.effective_microusd)}</div><div role="progressbar" aria-label="Application cap used" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(percent)} className="h-2 rounded bg-muted mt-3"><div className="h-2 rounded bg-primary" style={{ width: `${percent}%` }} /></div></CardContent></Card>
      <Card><CardHeader><CardTitle className="text-sm">Application headroom</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{usd(data.remaining_microusd)}</div><p className="text-xs cron-muted">Cap {usd(data.application_cap_microusd)}</p></CardContent></Card>
      <Card><CardHeader><CardTitle className="text-sm">Live compute</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{data.live_count}</div><p className="text-xs cron-muted">{data.termination_uncertain_count} termination uncertain</p></CardContent></Card>
    </div>
    <Card><CardHeader><CardTitle>Accounting and policy</CardTitle><CardDescription>{data.environment} · cycle {data.billing_cycle}</CardDescription></CardHeader><CardContent className="grid md:grid-cols-3 gap-4 text-sm">
      <label><strong>Environment</strong><select aria-label="Chat compute environment" value={data.environment} disabled className="block mt-1"><option>{data.environment}</option></select></label>
      <div><strong>Conservative estimate</strong><br />{usd(data.estimated_microusd)}</div>
      <div><strong>Provider-reported floor</strong><br />{usd(data.provider_floor_microusd)} · <Badge>{reconciliationLabel}</Badge></div>
      <div><strong>Provider backstops</strong><br />Environment {usd(data.environment_cap_microusd)} · Workspace {usd(data.workspace_cap_microusd)}</div>
      <div><strong>Active thresholds</strong><br />Warning {usd(data.warning_microusd)} · trip {usd(data.application_cap_microusd)}</div>
      <div><strong>Policy allocation</strong><br />Staging now $75/$100/$125 · staging with prod $15/$20/$25 · production $175/$200/$225 · workspace $250</div>
      <div><strong>Cycle end</strong><br />{formatCronDate(data.cycle_end_at)}</div>
      <div><strong>Last metered</strong><br />{data.last_metered_at ? formatCronDate(data.last_metered_at) : "Unavailable"}</div>
      <div><strong>Provider reconciliation</strong><br />{data.last_reconciled_at ? formatCronDate(data.last_reconciled_at) : "Unavailable"}{data.next_reconciliation_at ? ` · next ${formatCronDate(data.next_reconciliation_at)}` : ""}</div>
      <div><strong>Burn projection</strong><br />{data.burn_rate_microusd_per_hour === null ? "Not enough data" : `${usd(data.burn_rate_microusd_per_hour)}/hour`}</div>
    </CardContent></Card>
    <Card><CardHeader><CardTitle>Live lifecycle</CardTitle></CardHeader><CardContent className="text-sm">{Object.entries(data.live_states).map(([state, count]) => <span className="mr-4" key={state}>{state}: {count}</span>)}</CardContent></Card>
    <Card><CardHeader><CardTitle>Daily spend</CardTitle></CardHeader><CardContent>{data.daily_spend.length ? <ul className="space-y-1 text-sm">{data.daily_spend.map((day) => <li key={day.date}>{day.date}: blank {usd(day.blank_pool_microusd)} · assigned {usd(day.assigned_microusd)}</li>)}</ul> : <p className="cron-muted">No compute recorded in this cycle.</p>}</CardContent></Card>
    <Card><CardHeader><CardTitle>Recent circuit events</CardTitle><CardDescription>Runbook: docs/chat-sandbox-spend-runbook.md</CardDescription></CardHeader><CardContent>{data.events.length ? <ul className="space-y-2 text-sm">{data.events.map((event) => <li key={event.id}><Badge>{event.severity}</Badge> {event.type} · {formatCronDate(event.created_at)}</li>)}</ul> : <p className="cron-muted">No events in this cycle.</p>}</CardContent></Card>
  </div>;
};

const CronDashboard = () => {
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshToken, setRefreshToken] = useState(0);
  const [expandedJobs, setExpandedJobs] = useState<Set<string>>(new Set());
  const { user } = useAuth();

  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ["cronStatus", user?.username],
    queryFn: () => apiClient.getCronStatus(),
    enabled: !!user?.is_admin,
    refetchInterval: autoRefresh ? 30000 : false,
    retry: false,
  });
  const paperMarkdownJobsQuery = useQuery({
    queryKey: ["paperMarkdownJobs", user?.username],
    queryFn: () => apiClient.getPaperMarkdownJobs(),
    enabled: !!user?.is_admin,
    refetchInterval: autoRefresh ? 30000 : false,
    retry: false,
  });
  const chatSpendQuery = useQuery({
    queryKey: ["chatSandboxSpend", user?.username],
    queryFn: () => apiClient.getChatSandboxSpend(),
    enabled: !!user?.is_admin,
    refetchInterval: autoRefresh ? 30000 : false,
    retry: false,
  });

  const errorStatus = error && typeof error === "object" && "status" in error ? error.status : undefined;
  const errorMessage = errorStatus === 401
    ? "Unauthorized. Sign in with an allowlisted Hugging Face admin account."
    : error instanceof Error ? error.message : undefined;

  const toggleJobExpansion = (jobName: string) => {
    setExpandedJobs((prev) => {
      const next = new Set(prev);
      if (next.has(jobName)) next.delete(jobName);
      else next.add(jobName);
      return next;
    });
  };

  const criticalJobs = data?.jobs.filter((job) => job.critical) ?? [];
  const otherJobs = data?.jobs.filter((job) => !job.critical) ?? [];

  const jobsByCategory = otherJobs.reduce((acc, job) => {
    if (!acc[job.category]) acc[job.category] = [];
    acc[job.category].push(job);
    return acc;
  }, {} as Record<string, CronJobStatus[]>);

  const sortedCategories = Object.keys(jobsByCategory).sort((a, b) => {
    const order = ["hourly", "daily", "weekly"];
    return order.indexOf(a) - order.indexOf(b);
  });

  const renderJobCard = (job: CronJobStatus) => (
    <CronJobCard
      key={job.job_name}
      job={job}
      expanded={expandedJobs.has(job.job_name)}
      onToggle={() => toggleJobExpansion(job.job_name)}
      paperMarkdownJobs={
        job.job_name === "paper_markdown_backfill"
          ? paperMarkdownJobsQuery.data
          : undefined
      }
      paperMarkdownJobsLoading={
        job.job_name === "paper_markdown_backfill"
          ? paperMarkdownJobsQuery.isLoading
          : false
      }
      paperMarkdownJobsError={
        job.job_name === "paper_markdown_backfill"
          ? paperMarkdownJobsQuery.error
          : null
      }
    />
  );

  const refreshAll = () => {
    setRefreshToken((value) => value + 1);
    void refetch();
    void paperMarkdownJobsQuery.refetch();
    void chatSpendQuery.refetch();
  };

  return (
    <div className="cron-dashboard" data-shadcn>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div>
              <h1 className="text-3xl font-bold flex items-center gap-3">
                <Activity className="h-8 w-8 cron-info-text" />
                Admin Dashboard
              </h1>
              <p className="mt-2 cron-muted">
                Paper curation queue and operational health for scheduled jobs
              </p>
            </div>
            <div className="flex items-center gap-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setAutoRefresh(!autoRefresh)}
                className={autoRefresh ? "cron-status--running" : ""}
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${autoRefresh ? "animate-spin" : ""}`} />
                Auto-refresh {autoRefresh ? "ON" : "OFF"}
              </Button>
              <Button variant="outline" size="sm" onClick={refreshAll} disabled={isFetching}>
                <RefreshCw className={`h-4 w-4 mr-2 ${isFetching ? "animate-spin" : ""}`} />
                Refresh
              </Button>
            </div>
          </div>
        </div>

        <Card className="mb-6">
          <CardContent className="pt-6">
            <p className="text-sm cron-muted">
              Signed in as <span className="font-semibold">@{user?.username}</span>. Health checks prefer
              database freshness over log completion so silent no-work failures surface as degraded or broken.
            </p>
          </CardContent>
        </Card>

        <Tabs defaultValue="critical-jobs">
          <TabsList className="grid w-full grid-cols-4 sm:w-auto">
            <TabsTrigger value="critical-jobs">Critical Jobs</TabsTrigger>
            <TabsTrigger value="codex-paper-jobs">Codex Paper Jobs</TabsTrigger>
            <TabsTrigger value="catalog-audit">Catalog Audit</TabsTrigger>
            <TabsTrigger value="chat-compute">Chat Compute</TabsTrigger>
          </TabsList>

          <TabsContent value="critical-jobs" className="mt-6">
            {isLoading && (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin cron-info-text" />
                <span className="ml-3 cron-muted">Loading CRON jobs status...</span>
              </div>
            )}

            {error && (
              <Card className="cron-status--broken">
                <CardContent className="pt-6">
                  <div className="flex items-center gap-3">
                    <XCircle className="h-5 w-5" />
                    <p>{errorMessage ?? "Failed to load CRON jobs status. Please try again."}</p>
                  </div>
                </CardContent>
              </Card>
            )}

            {data && (
              <>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
              {(["healthy", "degraded", "broken", "running", "stuck", "unknown"] as CronJobHealth[]).map(
                (status) => (
                  <Card key={status}>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium cron-muted capitalize">
                        {status}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="text-2xl font-bold">{data.summary[status]}</div>
                    </CardContent>
                  </Card>
                ),
              )}
            </div>

            {data.summary.critical_issues.length > 0 && (
              <Card className="mb-6 cron-status--broken">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <ShieldAlert className="h-5 w-5" />
                    Critical job issues
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="list-disc pl-5 space-y-1 text-sm">
                    {data.summary.critical_issues.map((issue) => (
                      <li key={issue}>{issue}</li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}

            <Card className="mb-8">
              <CardHeader>
                <CardTitle className="text-base">What to check next</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm cron-muted">{data.summary.what_to_check_next}</p>
                <p className="mt-2 text-xs cron-muted flex items-center gap-2">
                  <Clock className="h-4 w-4" />
                  Last updated: {formatCronDate(data.timestamp)} · Health score:{" "}
                  {data.summary.health_score.toFixed(0)}%
                </p>
              </CardContent>
            </Card>

            <Card className="mb-8">
              <CardHeader>
                <CardTitle className="text-xl">Critical jobs</CardTitle>
                <CardDescription>Writers whose stale output breaks the live site</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {criticalJobs.map(renderJobCard)}
              </CardContent>
            </Card>

            <div className="space-y-6">
              {sortedCategories.map((category) => (
                <Card key={category}>
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-xl capitalize flex items-center gap-2">
                        <Badge className={categoryColors[category] ?? categoryColors.hourly}>
                          {category}
                        </Badge>
                        <span>Supporting jobs</span>
                      </CardTitle>
                      <CardDescription>
                        {jobsByCategory[category].length} job
                        {jobsByCategory[category].length !== 1 ? "s" : ""}
                      </CardDescription>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {jobsByCategory[category].map(renderJobCard)}
                  </CardContent>
                </Card>
              ))}
            </div>
              </>
            )}
          </TabsContent>

          <TabsContent value="codex-paper-jobs" className="mt-6">
            <CodexJobQueue autoRefresh={autoRefresh} refreshToken={refreshToken} />
          </TabsContent>
          <TabsContent value="catalog-audit" className="mt-6">
            <CatalogAuditPanel />
          </TabsContent>
          <TabsContent value="chat-compute" className="mt-6">
            <ChatComputePanel data={chatSpendQuery.data} loading={chatSpendQuery.isLoading} error={chatSpendQuery.error} />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
};

export default CronDashboard;
