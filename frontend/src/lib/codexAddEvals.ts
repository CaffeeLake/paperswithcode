import { apiUrl } from "@/lib/apiUrl";

export type CodexPaperJobStatus = "queued" | "dispatching" | "running" | "completed" | "failed" | "canceled";

export interface CodexPaperJob {
  id: string;
  paper_id: number;
  paper_route: string;
  paper_title: string;
  requested_by: string;
  kind: "add-evals" | "enrich-paper";
  status: CodexPaperJobStatus;
  hf_job_id: string | null;
  hf_job_url: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  applied_at: string | null;
  report: string | null;
  error: string | null;
  attempt_count: number;
}

export interface CodexPaperJobsResponse {
  timestamp: string;
  jobs: CodexPaperJob[];
  summary: Record<CodexPaperJobStatus, number> & { total: number };
}

export function isCodexAddEvalsEnabled(): boolean {
  const value = String(import.meta.env.VITE_CODEX_ADD_EVALS_ENABLED ?? "").toLowerCase();
  return value === "1" || value === "true" || value === "yes";
}

export function isCodexEnrichPaperEnabled(): boolean {
  const value = String(import.meta.env.VITE_CODEX_ENRICH_PAPER_ENABLED ?? "").toLowerCase();
  return value === "1" || value === "true" || value === "yes";
}

async function readJobResponse(response: Response): Promise<CodexPaperJob> {
  if (response.ok) return (await response.json()) as CodexPaperJob;
  const body = await response.json().catch(() => null);
  const detail = body?.detail?.message ?? body?.detail;
  throw new Error(typeof detail === "string" ? detail : "Could not run Codex.");
}

export async function startCodexAddEvals(paperId: number): Promise<CodexPaperJob> {
  const response = await fetch(apiUrl("/api/v1/admin/codex-add-evals/jobs"), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paper_id: paperId }),
  });
  return readJobResponse(response);
}

export async function getCodexAddEvalsJob(jobId: string): Promise<CodexPaperJob> {
  const response = await fetch(apiUrl(`/api/v1/admin/codex-add-evals/jobs/${jobId}`), {
    credentials: "include",
  });
  return readJobResponse(response);
}

export async function cancelCodexAddEvalsJob(jobId: string): Promise<CodexPaperJob> {
  return readJobResponse(await fetch(apiUrl(`/api/v1/admin/codex-add-evals/jobs/${jobId}`), {
    method: "DELETE", credentials: "include",
  }));
}

export async function startCodexEnrichPaper(paperId: number): Promise<CodexPaperJob> {
  const response = await fetch(apiUrl("/api/v1/admin/codex-enrich-paper/jobs"), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paper_id: paperId }),
  });
  return readJobResponse(response);
}

export async function getCodexEnrichPaperJob(jobId: string): Promise<CodexPaperJob> {
  const response = await fetch(apiUrl(`/api/v1/admin/codex-enrich-paper/jobs/${jobId}`), {
    credentials: "include",
  });
  return readJobResponse(response);
}

export async function cancelCodexEnrichPaperJob(jobId: string): Promise<CodexPaperJob> {
  return readJobResponse(await fetch(apiUrl(`/api/v1/admin/codex-enrich-paper/jobs/${jobId}`), {
    method: "DELETE", credentials: "include",
  }));
}

export async function getCodexPaperJobs(limit = 100): Promise<CodexPaperJobsResponse> {
  const response = await fetch(
    apiUrl(`/api/v1/admin/codex-curation/jobs?limit=${limit}`),
    { credentials: "include", cache: "no-store" },
  );
  if (response.ok) return (await response.json()) as CodexPaperJobsResponse;
  const error = new Error(`Could not load Codex jobs (${response.status}).`);
  Object.assign(error, { status: response.status });
  throw error;
}
