import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Loader2,
  Activity,
  Calendar,
  TrendingUp,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  FileText,
  Database,
  ShieldAlert,
  AlertTriangle,
} from "lucide-react";
import { apiUrl } from "@/lib/apiUrl";
import { useAuth } from "@/lib/authContext";

type JobStatus = "healthy" | "degraded" | "broken" | "running" | "stuck" | "unknown";

interface CronJobStatus {
  job_name: string;
  display_name: string;
  category: string;
  status: JobStatus;
  log_status?: string | null;
  status_reason: string;
  last_run: string | null;
  last_db_write: string | null;
  recent_write_count: number | null;
  duration: number | null;
  is_running: boolean;
  error: string | null;
  schedule: string | null;
  critical: boolean;
  work_metrics?: Record<string, string | number>;
  work_summary?: string | null;
  db_metrics?: Record<string, string | number>;
  lock_stale?: boolean;
  diagnostics?: string | null;
}

interface CronJobsResponse {
  timestamp: string;
  jobs: CronJobStatus[];
  summary: {
    total_jobs: number;
    healthy: number;
    degraded: number;
    broken: number;
    running: number;
    stuck: number;
    unknown: number;
    health_score: number;
    critical_issues: string[];
    what_to_check_next: string;
  };
}

const fetchCronStatus = async (): Promise<CronJobsResponse> => {
  const response = await fetch(apiUrl("/api/v1/cron/status"), {
    credentials: "include",
  });

  if (response.status === 401) {
    throw new Error("Unauthorized. Sign in with an allowlisted Hugging Face admin account.");
  }

  if (!response.ok) {
    throw new Error("Failed to fetch cron status");
  }
  return response.json();
};

const StatusIcon = ({ status, isRunning }: { status: JobStatus; isRunning: boolean }) => {
  if (isRunning || status === "running") {
    return <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />;
  }

  switch (status) {
    case "healthy":
      return <CheckCircle2 className="h-5 w-5 text-green-500" />;
    case "degraded":
      return <AlertTriangle className="h-5 w-5 text-yellow-500" />;
    case "broken":
    case "stuck":
      return <XCircle className="h-5 w-5 text-red-500" />;
    default:
      return <AlertCircle className="h-5 w-5 text-gray-400" />;
  }
};

const statusStyles: Record<JobStatus, string> = {
  healthy: "bg-green-50 text-green-700 border-green-300",
  degraded: "bg-yellow-50 text-yellow-800 border-yellow-300",
  broken: "bg-red-50 text-red-700 border-red-300",
  running: "bg-blue-50 text-blue-700 border-blue-300",
  stuck: "bg-red-50 text-red-700 border-red-300",
  unknown: "bg-gray-50 text-gray-700 border-gray-300",
};

const StatusBadge = ({ status }: { status: JobStatus }) => (
  <Badge variant="outline" className={statusStyles[status]}>
    {status.replace("_", " ")}
  </Badge>
);

const formatDate = (dateString: string | null): string => {
  if (!dateString) return "Never";

  try {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dateString;
  }
};

const formatDuration = (duration: number | null): string => {
  if (duration == null) return "N/A";
  if (duration < 60) return `${duration.toFixed(1)}s`;
  if (duration < 3600) return `${(duration / 60).toFixed(1)}m`;
  return `${(duration / 3600).toFixed(1)}h`;
};

const categoryColors: Record<string, string> = {
  hourly: "bg-blue-100 text-blue-800 border-blue-200",
  daily: "bg-purple-100 text-purple-800 border-purple-200",
  weekly: "bg-orange-100 text-orange-800 border-orange-200",
};

const metricLabel = (key: string): string =>
  key.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());

const CronDashboard = () => {
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [expandedJobs, setExpandedJobs] = useState<Set<string>>(new Set());
  const { user } = useAuth();

  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ["cronStatus", user?.username],
    queryFn: fetchCronStatus,
    enabled: !!user?.is_admin,
    refetchInterval: autoRefresh ? 30000 : false,
    retry: false,
  });

  const errorMessage = error instanceof Error ? error.message : undefined;

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

  const renderJobCard = (job: CronJobStatus) => {
    const isExpanded = expandedJobs.has(job.job_name);
    const hasMetrics =
      (job.work_metrics && Object.keys(job.work_metrics).length > 0) ||
      (job.db_metrics && Object.keys(job.db_metrics).length > 0);

    return (
      <div key={job.job_name} className="border rounded-lg overflow-hidden transition-all">
        <div
          className="p-4 hover:bg-gray-50 transition-colors cursor-pointer"
          onClick={() => toggleJobExpansion(job.job_name)}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-start gap-3 flex-1 min-w-0">
              <StatusIcon status={job.status} isRunning={job.is_running} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                  <h3 className="font-semibold text-gray-900">{job.display_name}</h3>
                  {job.critical && (
                    <Badge variant="outline" className="text-[10px] uppercase tracking-wide">
                      Critical
                    </Badge>
                  )}
                  {job.lock_stale && (
                    <Badge variant="outline" className="bg-red-50 text-red-700 border-red-200">
                      Stale lock
                    </Badge>
                  )}
                  {hasMetrics && (
                    isExpanded ? <ChevronUp className="h-4 w-4 text-gray-400" /> : <ChevronDown className="h-4 w-4 text-gray-400" />
                  )}
                </div>
                <p className="text-sm text-gray-600 mb-2">{job.status_reason}</p>
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-2 text-sm text-gray-600">
                  <div className="flex items-center gap-1">
                    <Clock className="h-4 w-4 shrink-0" />
                    <span>Log: {formatDate(job.last_run)}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Database className="h-4 w-4 shrink-0" />
                    <span>DB: {formatDate(job.last_db_write)}</span>
                  </div>
                  {job.recent_write_count != null && (
                    <div className="flex items-center gap-1">
                      <TrendingUp className="h-4 w-4 shrink-0" />
                      <span>Recent writes: {job.recent_write_count.toLocaleString()}</span>
                    </div>
                  )}
                  {job.duration != null && (
                    <div className="flex items-center gap-1">
                      <Activity className="h-4 w-4 shrink-0" />
                      <span>Duration: {formatDuration(job.duration)}</span>
                    </div>
                  )}
                  {job.schedule && (
                    <div className="flex items-center gap-1 md:col-span-2">
                      <Calendar className="h-4 w-4 shrink-0" />
                      <span className="font-mono text-xs">{job.schedule}</span>
                    </div>
                  )}
                  {job.log_status && (
                    <div className="flex items-center gap-1">
                      <FileText className="h-4 w-4 shrink-0" />
                      <span>Log status: {job.log_status}</span>
                    </div>
                  )}
                </div>
                {job.work_summary && (
                  <div className="mt-2 text-sm text-gray-600 bg-gray-100 rounded px-2 py-1">
                    {job.work_summary}
                  </div>
                )}
                {job.error && (
                  <div className="mt-2 text-sm text-red-600 bg-red-50 rounded px-2 py-1">
                    <span className="font-semibold">Error: </span>
                    {job.error}
                  </div>
                )}
                {job.diagnostics && (
                  <div className="mt-2 text-sm text-amber-800 bg-amber-50 rounded px-2 py-1">
                    {job.diagnostics}
                  </div>
                )}
              </div>
            </div>
            <StatusBadge status={job.status} />
          </div>
        </div>

        {isExpanded && hasMetrics && (
          <div className="border-t bg-gray-50 p-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {job.work_metrics && Object.keys(job.work_metrics).length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <FileText className="h-4 w-4 text-gray-600" />
                    <h4 className="font-semibold text-gray-700">Log Metrics</h4>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    {Object.entries(job.work_metrics).map(([key, value]) => (
                      <div key={key} className="bg-white rounded border border-gray-200 p-3">
                        <div className="text-xs text-gray-500 mb-1">{metricLabel(key)}</div>
                        <div className="text-lg font-semibold text-gray-900">
                          {typeof value === "number" ? value.toLocaleString() : value}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {job.db_metrics && Object.keys(job.db_metrics).length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <Database className="h-4 w-4 text-gray-600" />
                    <h4 className="font-semibold text-gray-700">Database Metrics</h4>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    {Object.entries(job.db_metrics).map(([key, value]) => (
                      <div key={key} className="bg-white rounded border border-gray-200 p-3">
                        <div className="text-xs text-gray-500 mb-1">{metricLabel(key)}</div>
                        <div className="text-lg font-semibold text-gray-900">
                          {typeof value === "number" ? value.toLocaleString() : value}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white" data-shadcn>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div>
              <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-3">
                <Activity className="h-8 w-8 text-blue-600" />
                CRON Health Dashboard
              </h1>
              <p className="mt-2 text-gray-600">
                Operational view for scheduled VPS jobs — log status plus database freshness
              </p>
            </div>
            <div className="flex items-center gap-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setAutoRefresh(!autoRefresh)}
                className={autoRefresh ? "border-blue-500 text-blue-600" : ""}
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${autoRefresh ? "animate-spin" : ""}`} />
                Auto-refresh {autoRefresh ? "ON" : "OFF"}
              </Button>
              <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
                <RefreshCw className={`h-4 w-4 mr-2 ${isFetching ? "animate-spin" : ""}`} />
                Refresh
              </Button>
            </div>
          </div>
        </div>

        <Card className="mb-6">
          <CardContent className="pt-6">
            <p className="text-sm text-gray-700">
              Signed in as <span className="font-semibold">@{user?.username}</span>. Health checks prefer
              database freshness over log completion so silent no-work failures surface as degraded or broken.
            </p>
          </CardContent>
        </Card>

        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
            <span className="ml-3 text-gray-600">Loading CRON jobs status...</span>
          </div>
        )}

        {error && (
          <Card className="border-red-200 bg-red-50">
            <CardContent className="pt-6">
              <div className="flex items-center gap-3 text-red-800">
                <XCircle className="h-5 w-5" />
                <p>{errorMessage ?? "Failed to load CRON jobs status. Please try again."}</p>
              </div>
            </CardContent>
          </Card>
        )}

        {data && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
              {(["healthy", "degraded", "broken", "running", "stuck", "unknown"] as JobStatus[]).map(
                (status) => (
                  <Card key={status}>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium text-gray-600 capitalize">
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
              <Card className="mb-6 border-red-200 bg-red-50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-red-800">
                    <ShieldAlert className="h-5 w-5" />
                    Critical job issues
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="list-disc pl-5 space-y-1 text-sm text-red-800">
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
                <p className="text-sm text-gray-700">{data.summary.what_to_check_next}</p>
                <p className="mt-2 text-xs text-gray-500 flex items-center gap-2">
                  <Clock className="h-4 w-4" />
                  Last updated: {formatDate(data.timestamp)} · Health score:{" "}
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
                        <span className="text-gray-700">Supporting jobs</span>
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
      </div>
    </div>
  );
};

export default CronDashboard;
