import type {
  PendingEditStatus,
  PendingEditType,
  PendingPaperEdit,
  PendingPaperEditSubmitPayload,
  PendingPaperEditsResponse,
} from "../api";
import type { ApiRequest } from "../apiTransport";
import { apiRequest } from "./request";

export class SubmissionsApi {
  constructor(private readonly request: ApiRequest) {}

  submit(payload: PendingPaperEditSubmitPayload): Promise<PendingPaperEdit> {
    return this.request("/me/paper-edits", { method: "POST", body: JSON.stringify(payload) });
  }

  list(params?: {
    status?: PendingEditStatus;
    edit_type?: PendingEditType;
    paper_id?: number;
    limit?: number;
    offset?: number;
  }): Promise<PendingPaperEditsResponse> {
    const searchParams = new URLSearchParams();
    for (const [key, value] of Object.entries(params ?? {})) {
      if (value !== undefined) searchParams.set(key, String(value));
    }
    const query = searchParams.toString();
    return this.request(`/admin/paper-edits${query ? `?${query}` : ""}`);
  }

  get(id: number): Promise<PendingPaperEdit> {
    return this.request(`/admin/paper-edits/${id}`);
  }

  approve(
    id: number,
    body: { admin_note?: string; user_review_reason?: string; resolved_payload?: Record<string, unknown> } = {},
  ): Promise<PendingPaperEdit> {
    return this.request(`/admin/paper-edits/${id}/approve`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  reject(
    id: number,
    body: { admin_note?: string; user_review_reason?: string } = {},
  ): Promise<PendingPaperEdit> {
    return this.request(`/admin/paper-edits/${id}/reject`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }
}

export const submissionsApi = new SubmissionsApi(apiRequest);
