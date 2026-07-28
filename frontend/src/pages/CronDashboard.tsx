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
import { apiClient } from "@/lib/api";
import type { CronJobHealth, CronJobStatus } from "@/lib/api";
import { formatCronDate } from "@/lib/cronStatus";
import { useAuth } from "@/lib/authContext";
import "./CronDashboard.css";

const categoryColors: Record<string, string> = {
  hourly: "cron-status--running",
  daily: "cron-status--healthy",
  weekly: "cron-status--degraded",
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
          <TabsList className="grid w-full grid-cols-2 sm:w-auto">
            <TabsTrigger value="critical-jobs">Critical Jobs</TabsTrigger>
            <TabsTrigger value="codex-paper-jobs">Codex Paper Jobs</TabsTrigger>
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
        </Tabs>
      </div>
    </div>
  );
};

export default CronDashboard;
