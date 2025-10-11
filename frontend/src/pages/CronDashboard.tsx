import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Header from "@/components/Header";
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
  RefreshCw
} from "lucide-react";

interface CronJobStatus {
  job_name: string;
  category: string;
  status: string;
  last_run: string | null;
  duration: number | null;
  is_running: boolean;
  error: string | null;
  next_run: string | null;
  schedule: string | null;
}

interface CronJobsResponse {
  timestamp: string;
  jobs: CronJobStatus[];
  summary: {
    total_jobs: number;
    success: number;
    failed: number;
    running: number;
    unknown: number;
    health_score: number;
  };
}

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Fetch cron jobs status
const fetchCronStatus = async (): Promise<CronJobsResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/v1/cron/status`);
  if (!response.ok) {
    throw new Error("Failed to fetch cron status");
  }
  return response.json();
};

// Status icon component
const StatusIcon = ({ status, isRunning }: { status: string; isRunning: boolean }) => {
  if (isRunning) {
    return <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />;
  }

  switch (status) {
    case "success":
      return <CheckCircle2 className="h-5 w-5 text-green-500" />;
    case "failed":
      return <XCircle className="h-5 w-5 text-red-500" />;
    case "running":
      return <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />;
    default:
      return <AlertCircle className="h-5 w-5 text-gray-400" />;
  }
};

// Status badge component
const StatusBadge = ({ status, isRunning }: { status: string; isRunning: boolean }) => {
  if (isRunning) {
    return (
      <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-300">
        Running
      </Badge>
    );
  }

  switch (status) {
    case "success":
      return (
        <Badge variant="outline" className="bg-green-50 text-green-700 border-green-300">
          Success
        </Badge>
      );
    case "failed":
      return (
        <Badge variant="outline" className="bg-red-50 text-red-700 border-red-300">
          Failed
        </Badge>
      );
    default:
      return (
        <Badge variant="outline" className="bg-gray-50 text-gray-700 border-gray-300">
          Unknown
        </Badge>
      );
  }
};

// Format job name for display
const formatJobName = (jobName: string): string => {
  return jobName
    .replace(/_/g, " ")
    .split(" ")
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
};

// Format date for display (past dates)
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
      minute: "2-digit"
    });
  } catch {
    return dateString;
  }
};

// Format future date for display (next run times)
const formatFutureDate = (dateString: string | null): string => {
  if (!dateString) return "Not scheduled";

  try {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = date.getTime() - now.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    // If it's in the past, show it's overdue
    if (diffMs < 0) {
      return "Overdue";
    }

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `in ${diffMins}m`;
    if (diffHours < 24) return `in ${diffHours}h`;
    if (diffDays < 7) return `in ${diffDays}d`;

    return date.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    });
  } catch {
    return dateString;
  }
};

// Format duration
const formatDuration = (duration: number | null): string => {
  if (!duration) return "N/A";

  if (duration < 60) {
    return `${duration.toFixed(1)}s`;
  } else if (duration < 3600) {
    return `${(duration / 60).toFixed(1)}m`;
  } else {
    return `${(duration / 3600).toFixed(1)}h`;
  }
};

// Category color mapping
const categoryColors: Record<string, string> = {
  hourly: "bg-blue-100 text-blue-800 border-blue-200",
  daily: "bg-purple-100 text-purple-800 border-purple-200",
  weekly: "bg-orange-100 text-orange-800 border-orange-200",
  monthly: "bg-pink-100 text-pink-800 border-pink-200"
};

const CronDashboard = () => {
  const [autoRefresh, setAutoRefresh] = useState(true);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["cronStatus"],
    queryFn: fetchCronStatus,
    refetchInterval: autoRefresh ? 30000 : false, // Auto-refresh every 30 seconds if enabled
  });

  // Group jobs by category
  const jobsByCategory = data?.jobs.reduce((acc, job) => {
    if (!acc[job.category]) {
      acc[job.category] = [];
    }
    acc[job.category].push(job);
    return acc;
  }, {} as Record<string, CronJobStatus[]>) || {};

  // Sort categories (hourly, daily, weekly, monthly)
  const sortedCategories = Object.keys(jobsByCategory).sort((a, b) => {
    const order = ["hourly", "daily", "weekly", "monthly"];
    return order.indexOf(a) - order.indexOf(b);
  });

  // Calculate health status color
  const getHealthColor = (score: number): string => {
    if (score >= 80) return "text-green-600";
    if (score >= 60) return "text-yellow-600";
    return "text-red-600";
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white">
      <Header />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Page Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-3">
                <Activity className="h-8 w-8 text-blue-600" />
                CRON Job Dashboard
              </h1>
              <p className="mt-2 text-gray-600">
                Monitor and manage automated tasks
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
              <Button
                variant="outline"
                size="sm"
                onClick={() => refetch()}
                disabled={isLoading}
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? "animate-spin" : ""}`} />
                Refresh
              </Button>
            </div>
          </div>
        </div>

        {/* Loading State */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
            <span className="ml-3 text-gray-600">Loading CRON jobs status...</span>
          </div>
        )}

        {/* Error State */}
        {error && (
          <Card className="border-red-200 bg-red-50">
            <CardContent className="pt-6">
              <div className="flex items-center gap-3 text-red-800">
                <XCircle className="h-5 w-5" />
                <p>Failed to load CRON jobs status. Please try again.</p>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Summary Cards */}
        {data && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-8">
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium text-gray-600">
                    Total Jobs
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">{data.summary.total_jobs}</div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium text-gray-600">
                    Successful
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-green-600">
                    {data.summary.success}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium text-gray-600">
                    Failed
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-red-600">
                    {data.summary.failed}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium text-gray-600">
                    Running
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-blue-600">
                    {data.summary.running}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium text-gray-600">
                    Health Score
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className={`text-2xl font-bold ${getHealthColor(data.summary.health_score)}`}>
                    {data.summary.health_score.toFixed(0)}%
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Last Updated */}
            <div className="mb-6 text-sm text-gray-500 flex items-center gap-2">
              <Clock className="h-4 w-4" />
              Last updated: {formatDate(data.timestamp)}
            </div>

            {/* Jobs by Category */}
            <div className="space-y-6">
              {sortedCategories.map((category) => (
                <Card key={category}>
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-xl capitalize flex items-center gap-2">
                        <Badge className={categoryColors[category]}>
                          {category}
                        </Badge>
                        <span className="text-gray-700">{category} Jobs</span>
                      </CardTitle>
                      <CardDescription>
                        {jobsByCategory[category].length} job{jobsByCategory[category].length !== 1 ? "s" : ""}
                      </CardDescription>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-4">
                      {jobsByCategory[category].map((job) => (
                        <div
                          key={job.job_name}
                          className="border rounded-lg p-4 hover:bg-gray-50 transition-colors"
                        >
                          <div className="flex items-start justify-between">
                            <div className="flex items-start gap-3 flex-1">
                              <StatusIcon status={job.status} isRunning={job.is_running} />
                              <div className="flex-1 min-w-0">
                                <h3 className="font-semibold text-gray-900 mb-1">
                                  {formatJobName(job.job_name)}
                                </h3>
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-2 text-sm text-gray-600">
                                  <div className="flex items-center gap-1">
                                    <Clock className="h-4 w-4" />
                                    <span>Last: {formatDate(job.last_run)}</span>
                                  </div>
                                  {job.duration && (
                                    <div className="flex items-center gap-1">
                                      <TrendingUp className="h-4 w-4" />
                                      <span>Duration: {formatDuration(job.duration)}</span>
                                    </div>
                                  )}
                                  {job.schedule && (
                                    <div className="flex items-center gap-1">
                                      <Calendar className="h-4 w-4" />
                                      <span className="font-mono text-xs">{job.schedule}</span>
                                    </div>
                                  )}
                                  {job.next_run && (
                                    <div className="flex items-center gap-1">
                                      <Activity className="h-4 w-4" />
                                      <span>Next: {formatFutureDate(job.next_run)}</span>
                                    </div>
                                  )}
                                </div>
                                {job.error && (
                                  <div className="mt-2 text-sm text-red-600 bg-red-50 rounded px-2 py-1">
                                    <span className="font-semibold">Error: </span>
                                    {job.error}
                                  </div>
                                )}
                              </div>
                            </div>
                            <StatusBadge status={job.status} isRunning={job.is_running} />
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>

            {/* Empty State */}
            {sortedCategories.length === 0 && (
              <Card>
                <CardContent className="pt-6">
                  <div className="text-center text-gray-500 py-12">
                    <Activity className="h-12 w-12 mx-auto mb-4 text-gray-400" />
                    <p>No CRON jobs found</p>
                  </div>
                </CardContent>
              </Card>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default CronDashboard;
