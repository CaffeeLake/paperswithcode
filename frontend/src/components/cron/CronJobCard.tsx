import {
  Activity,
  AlertCircle,
  AlertTriangle,
  Calendar,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Database,
  FileText,
  Loader2,
  TrendingUp,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { CronJobHealth, CronJobStatus, CronWorkflowStatus } from "@/lib/api";
import { formatCronDate } from "@/lib/cronStatus";

function formatDuration(duration: number | null): string {
  if (duration == null) return "N/A";
  if (duration < 60) return `${duration.toFixed(1)}s`;
  if (duration < 3600) return `${(duration / 60).toFixed(1)}m`;
  return `${(duration / 3600).toFixed(1)}h`;
}

function formatWorkflowStatus(workflow: CronWorkflowStatus): string {
  if (!workflow.available) return "Unavailable";
  if (workflow.status === "completed") return workflow.conclusion ?? "completed";
  return workflow.status ?? "unknown";
}

function metricLabel(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

const statusIcon = {
  healthy: CheckCircle2,
  degraded: AlertTriangle,
  broken: XCircle,
  running: Loader2,
  stuck: XCircle,
  unknown: AlertCircle,
} satisfies Record<CronJobHealth, typeof Activity>;

function Status({ status, isRunning }: { status: CronJobHealth; isRunning: boolean }) {
  const effectiveStatus = isRunning ? "running" : status;
  const StatusIcon = statusIcon[effectiveStatus];
  return (
    <StatusIcon
      className={`cron-status-icon cron-status--${effectiveStatus}${effectiveStatus === "running" ? " animate-spin" : ""}`}
    />
  );
}

function MetricGroup({
  icon: Icon,
  title,
  metrics,
}: {
  icon: typeof Activity;
  title: string;
  metrics: Record<string, string | number>;
}) {
  return (
    <div>
      <div className="cron-section-heading">
        <Icon className="h-4 w-4" />
        <h4>{title}</h4>
      </div>
      <div className="grid grid-cols-2 gap-3">
        {Object.entries(metrics).map(([key, value]) => (
          <div key={key} className="cron-metric-card">
            <div className="cron-label">{metricLabel(key)}</div>
            <div className="text-lg font-semibold">
              {typeof value === "number" ? value.toLocaleString() : value}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function WorkflowDetails({ workflow }: { workflow: CronWorkflowStatus }) {
  return (
    <div>
      <div className="cron-section-heading">
        <Activity className="h-4 w-4" />
        <h4>GitHub Actions</h4>
      </div>
      <div className="cron-metric-card space-y-2 text-sm">
        {[
          ["Workflow", workflow.workflow_file],
          ["Run", workflow.run_id ?? "N/A"],
          ["Status", formatWorkflowStatus(workflow)],
          ...(workflow.updated_at ? [["Updated", formatCronDate(workflow.updated_at)]] : []),
        ].map(([label, value]) => (
          <div key={label} className="flex items-center justify-between gap-3">
            <span className="cron-label">{label}</span>
            <span className={label === "Workflow" ? "font-mono text-xs" : undefined}>{value}</span>
          </div>
        ))}
        {workflow.failed_jobs && workflow.failed_jobs.length > 0 && (
          <div>
            <div className="cron-label mb-1">Failed jobs</div>
            <div className="flex gap-2 flex-wrap">
              {workflow.failed_jobs.map((jobName) => (
                <Badge key={jobName} variant="outline" className="cron-status--broken">{jobName}</Badge>
              ))}
            </div>
          </div>
        )}
        {workflow.job_conclusions && Object.keys(workflow.job_conclusions).length > 0 && (
          <div>
            <div className="cron-label mb-1">Job conclusions</div>
            <div className="flex gap-2 flex-wrap">
              {Object.entries(workflow.job_conclusions).map(([jobName, conclusion]) => (
                <Badge key={jobName} variant="outline">{jobName}: {conclusion ?? "running"}</Badge>
              ))}
            </div>
          </div>
        )}
        {(workflow.error || workflow.view_error) && (
          <div className="cron-message cron-message--error">{workflow.error ?? workflow.view_error}</div>
        )}
      </div>
    </div>
  );
}

export function CronJobCard({
  job,
  expanded,
  onToggle,
}: {
  job: CronJobStatus;
  expanded: boolean;
  onToggle: () => void;
}) {
  const hasWorkMetrics = Boolean(job.work_metrics && Object.keys(job.work_metrics).length);
  const hasDbMetrics = Boolean(job.db_metrics && Object.keys(job.db_metrics).length);
  const hasDetails = hasWorkMetrics || hasDbMetrics || Boolean(job.workflow_status);

  return (
    <div className="cron-job-card">
      <button type="button" className="cron-job-summary" onClick={onToggle} aria-expanded={expanded}>
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 flex-1 min-w-0">
            <Status status={job.status} isRunning={job.is_running} />
            <div className="flex-1 min-w-0 text-left">
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <h3 className="font-semibold">{job.display_name}</h3>
                {job.critical && <Badge variant="outline" className="text-[10px] uppercase tracking-wide">Critical</Badge>}
                {job.lock_stale && <Badge variant="outline" className="cron-status--broken">Stale lock</Badge>}
                {hasDetails && (expanded ? <ChevronUp className="h-4 w-4 cron-muted" /> : <ChevronDown className="h-4 w-4 cron-muted" />)}
              </div>
              <p className="text-sm cron-muted mb-2">{job.status_reason}</p>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-2 text-sm cron-muted">
                <span className="cron-fact"><Clock />Log: {formatCronDate(job.last_run)}</span>
                <span className="cron-fact"><Database />DB: {formatCronDate(job.last_db_write)}</span>
                {job.recent_write_count != null && <span className="cron-fact"><TrendingUp />Recent writes: {job.recent_write_count.toLocaleString()}</span>}
                {job.duration != null && <span className="cron-fact"><Activity />Duration: {formatDuration(job.duration)}</span>}
                {job.schedule && <span className="cron-fact md:col-span-2"><Calendar /><span className="font-mono text-xs">{job.schedule}</span></span>}
                {job.log_status && <span className="cron-fact"><FileText />Log status: {job.log_status}</span>}
                {job.workflow_status && <span className="cron-fact"><Activity />Actions: {formatWorkflowStatus(job.workflow_status)}</span>}
              </div>
              {job.work_summary && <div className="cron-message">{job.work_summary}</div>}
              {job.error && <div className="cron-message cron-message--error"><strong>Error: </strong>{job.error}</div>}
              {job.diagnostics && <div className="cron-message cron-message--warning">{job.diagnostics}</div>}
            </div>
          </div>
          <Badge variant="outline" className={`cron-status--${job.status}`}>{job.status}</Badge>
        </div>
      </button>

      {expanded && hasDetails && (
        <div className="cron-job-details">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {job.work_metrics && hasWorkMetrics && <MetricGroup icon={FileText} title="Log Metrics" metrics={job.work_metrics} />}
            {job.db_metrics && hasDbMetrics && <MetricGroup icon={Database} title="Database Metrics" metrics={job.db_metrics} />}
            {job.workflow_status && <WorkflowDetails workflow={job.workflow_status} />}
          </div>
        </div>
      )}
    </div>
  );
}
