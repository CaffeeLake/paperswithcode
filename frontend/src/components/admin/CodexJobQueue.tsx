import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle2,
  CircleSlash2,
  Clock3,
  ExternalLink,
  Loader2,
  PlayCircle,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatCronDate } from "@/lib/cronStatus";
import {
  getCodexPaperJobs,
  type CodexPaperJob,
  type CodexPaperJobStatus,
} from "@/lib/codexAddEvals";

const statusStyles: Record<CodexPaperJobStatus, string> = {
  queued: "cron-status--unknown",
  dispatching: "cron-status--running",
  running: "cron-status--running",
  completed: "cron-status--healthy",
  failed: "cron-status--broken",
  canceled: "cron-status--unknown",
};

const kindLabels: Record<CodexPaperJob["kind"], string> = {
  "add-evals": "Add evals",
  "enrich-paper": "Enrich paper",
};

const statusIcons: Record<CodexPaperJobStatus, typeof Clock3> = {
  queued: Clock3,
  dispatching: Loader2,
  running: PlayCircle,
  completed: CheckCircle2,
  failed: XCircle,
  canceled: CircleSlash2,
};

interface CodexJobQueueProps {
  autoRefresh: boolean;
  refreshToken: number;
}

function JobStatus({ status }: { status: CodexPaperJobStatus }) {
  const Icon = statusIcons[status];
  return (
    <Badge variant="outline" className={statusStyles[status]}>
      <Icon className={`mr-1 h-3.5 w-3.5 ${status === "dispatching" ? "animate-spin" : ""}`} />
      {status}
    </Badge>
  );
}

function resultText(job: CodexPaperJob) {
  if (job.error) return job.error;
  if (job.report) return job.report;
  if (job.status === "completed" && job.applied_at) return "Changes applied to the paper.";
  if (job.status === "completed") return "Completed without a recorded mutation.";
  return null;
}

export function CodexJobQueue({ autoRefresh, refreshToken }: CodexJobQueueProps) {
  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: ["codexPaperJobs", refreshToken],
    queryFn: () => getCodexPaperJobs(100),
    refetchInterval: autoRefresh ? 10_000 : false,
    retry: false,
  });

  const errorStatus = error && typeof error === "object" && "status" in error ? error.status : undefined;

  return (
    <Card className="mb-8">
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="text-xl">Codex paper jobs</CardTitle>
            <CardDescription>
              Durable queue and execution history for admin-triggered Hugging Face Jobs
            </CardDescription>
          </div>
          {isFetching && !isLoading && (
            <span className="flex items-center gap-2 text-xs cron-muted">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Syncing with Hugging Face
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="flex items-center justify-center py-10 cron-muted">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading paper jobs…
          </div>
        )}

        {error && errorStatus !== 404 && (
          <div className="cron-message cron-message--error mb-4">
            {error instanceof Error ? error.message : "Could not load Codex paper jobs."}
          </div>
        )}

        {errorStatus === 404 && (
          <p className="py-4 text-sm cron-muted">Codex paper jobs are not enabled in this environment.</p>
        )}

        {data && (
          <>
            <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
              {(["queued", "dispatching", "running", "completed", "failed", "canceled"] as const).map(
                (status) => (
                  <div className="cron-metric-card" key={status}>
                    <div className="cron-label capitalize">{status}</div>
                    <div className="mt-1 text-xl font-semibold">{data.summary[status]}</div>
                  </div>
                ),
              )}
              <div className="cron-metric-card">
                <div className="cron-label">Total</div>
                <div className="mt-1 text-xl font-semibold">{data.summary.total}</div>
              </div>
            </div>

            {data.jobs.length === 0 ? (
              <p className="py-8 text-center text-sm cron-muted">No paper curation jobs have been submitted yet.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Status</TableHead>
                    <TableHead>Paper</TableHead>
                    <TableHead>Action</TableHead>
                    <TableHead>Requested</TableHead>
                    <TableHead>Execution</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.jobs.map((job) => {
                    const detail = resultText(job);
                    return (
                      <TableRow key={job.id}>
                        <TableCell className="align-top"><JobStatus status={job.status} /></TableCell>
                        <TableCell className="min-w-[260px] align-top">
                          <Link
                            to={`/paper/${encodeURIComponent(job.paper_route)}`}
                            className="font-medium hover:underline"
                          >
                            {job.paper_title}
                          </Link>
                          <div className="mt-1 text-xs cron-muted">Paper #{job.paper_id}</div>
                        </TableCell>
                        <TableCell className="whitespace-nowrap align-top">
                          {kindLabels[job.kind]}
                          {job.applied_at && (
                            <div className="mt-1 flex items-center gap-1 text-xs cron-status--healthy">
                              <CheckCircle2 className="h-3.5 w-3.5" /> Applied
                            </div>
                          )}
                        </TableCell>
                        <TableCell className="whitespace-nowrap align-top">
                          <div>{formatCronDate(job.created_at)}</div>
                          <div className="mt-1 text-xs cron-muted">@{job.requested_by}</div>
                        </TableCell>
                        <TableCell className="max-w-[360px] align-top">
                          {job.hf_job_url ? (
                            <a
                              href={job.hf_job_url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 hover:underline"
                            >
                              Hugging Face Job <ExternalLink className="h-3.5 w-3.5" />
                            </a>
                          ) : (
                            <span className="cron-muted">Waiting to dispatch</span>
                          )}
                          {detail && (
                            <p
                              className={`mt-2 line-clamp-3 text-xs ${job.error ? "text-red-700" : "cron-muted"}`}
                              title={detail}
                            >
                              {detail}
                            </p>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
            <p className="mt-4 text-xs cron-muted">
              Showing the 100 most recent jobs · Queue totals include full history · Updated {formatCronDate(data.timestamp)}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
