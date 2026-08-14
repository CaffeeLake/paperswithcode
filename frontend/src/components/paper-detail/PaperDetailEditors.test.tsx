import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Paper } from "@/lib/api";
import type { PaperEditSection } from "@/hooks/usePaperEditState";
import { PaperDetailEditors } from "./PaperDetailEditors";

vi.mock("./EditTasksDialog", () => ({ EditTasksDialog: () => <div>tasks editor</div> }));
vi.mock("./EditMethodsDialog", () => ({ EditMethodsDialog: () => <div>methods editor</div> }));
vi.mock("./EditRepositoriesDialog", () => ({ EditRepositoriesDialog: () => <div>repositories editor</div> }));
vi.mock("./EditProjectPagesDialog", () => ({ EditProjectPagesDialog: () => <div>project-pages editor</div> }));
vi.mock("./EditEvaluationsDialog", () => ({ EditEvaluationsDialog: () => <div>results editor</div> }));
vi.mock("./EditSourceUrlDialog", () => ({ EditSourceUrlDialog: () => <div>source-url editor</div> }));
vi.mock("./EditHfArtifactsDialog", () => ({ EditHfArtifactsDialog: () => <div>hf-artifacts editor</div> }));
vi.mock("./EditOrganizationsDialog", () => ({ EditOrganizationsDialog: () => <div>organizations editor</div> }));

const paper: Paper = {
  id: "17",
  arxiv_id: "2608.00123",
  url_abs: "https://arxiv.org/abs/2608.00123",
  url_pdf: null,
  title: "Paper",
  abstract: "Abstract",
  authors: ["Author"],
  published: "2026-08-01",
  version: "v1",
  is_latest_version: true,
  citation_count: 0,
};

describe("PaperDetailEditors", () => {
  it.each([
    "tasks",
    "methods",
    "repositories",
    "project-pages",
    "results",
    "source-url",
    "hf-artifacts",
    "organizations",
  ] satisfies PaperEditSection[])("renders the registered %s editor", (activeEditor) => {
    render(
      <PaperDetailEditors
        activeEditor={activeEditor}
        arxivId="2608.00123"
        editSubmitMode="pending"
        evaluations={[]}
        isAdmin={false}
        isLinkedAuthor={false}
        onOpenChange={vi.fn()}
        paper={paper}
      />,
    );

    expect(screen.getByText(`${activeEditor} editor`)).toBeInTheDocument();
  });
});
