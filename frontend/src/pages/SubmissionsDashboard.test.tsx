import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { PendingPaperEdit } from "@/lib/api";
import SubmissionsDashboard from "@/pages/SubmissionsDashboard";

const { listPendingPaperEdits } = vi.hoisted(() => ({
  listPendingPaperEdits: vi.fn(),
}));

vi.mock("@/lib/authContext", () => ({
  useAuth: () => ({
    user: { is_admin: true },
    isLoading: false,
  }),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    listPendingPaperEdits,
  };
});

const externalPaperSubmission: PendingPaperEdit = {
  id: 1103,
  paper_id: null,
  hf_username: "submitter",
  is_author: false,
  edit_type: "new_external_paper",
  proposed_payload: {
    title: "A useful external paper",
    source_url: "https://example.com/paper",
    authors: ["Example Author"],
    date_published: "2026-08-10",
  },
  status: "pending",
  created_at: "2026-08-10T07:00:00Z",
  updated_at: "2026-08-10T07:00:00Z",
};

function taxonomySubmission(
  id: number,
  editType: "new_task" | "new_method" | "new_benchmark" | "new_metric" | "new_conference",
): PendingPaperEdit {
  return {
    ...externalPaperSubmission,
    id,
    edit_type: editType,
    proposed_payload: { name: `Suggestion ${id}` },
  };
}

function renderDashboard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <SubmissionsDashboard />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  listPendingPaperEdits.mockReset();
  listPendingPaperEdits.mockResolvedValue({
    count: 1,
    results: [externalPaperSubmission],
  });
});

describe("SubmissionsDashboard", () => {
  it("labels and filters external paper submissions separately from taxonomy suggestions", async () => {
    const user = userEvent.setup();
    renderDashboard();

    expect(
      await screen.findByText("External paper", { selector: ".submission-title" }),
    ).toBeInTheDocument();
    expect(screen.getByText("External paper submission")).toBeInTheDocument();
    expect(screen.queryByText("Taxonomy directory")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "external paper" }));

    await waitFor(() =>
      expect(listPendingPaperEdits).toHaveBeenCalledWith(
        expect.objectContaining({ edit_type: "new_external_paper" }),
      ),
    );
  });

  it("uses type-specific titles for taxonomy suggestions", async () => {
    const submissions = [
      taxonomySubmission(1, "new_task"),
      taxonomySubmission(2, "new_method"),
      taxonomySubmission(3, "new_benchmark"),
      taxonomySubmission(4, "new_metric"),
      taxonomySubmission(5, "new_conference"),
    ];
    listPendingPaperEdits.mockResolvedValue({
      count: submissions.length,
      results: submissions,
    });

    renderDashboard();

    for (const title of ["New task", "New method", "New benchmark", "New metric", "New conference"]) {
      expect(await screen.findByText(title, { selector: ".submission-title" })).toBeInTheDocument();
    }
    for (const subtitle of [
      "Task suggestion",
      "Method suggestion",
      "Benchmark suggestion",
      "Metric suggestion",
      "Conference suggestion",
    ]) {
      expect(screen.getByText(subtitle)).toBeInTheDocument();
    }
    expect(screen.queryByText("Taxonomy directory")).not.toBeInTheDocument();
  });
});
