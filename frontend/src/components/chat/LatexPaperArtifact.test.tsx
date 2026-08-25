import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ArtifactWorkspace } from "./ArtifactWorkspace";
import { LatexPaperArtifact } from "./LatexPaperArtifact";
import { ArtifactPanelProvider } from "./useArtifactPanel";

const descriptor = {
  artifact_id: "artifact-1",
  title: "Careful Draft",
  source_head: {
    version_id: "source-1",
    version: 2,
    source_digest: "a".repeat(64),
    compile_status: "failed" as const,
    preview_head_version_id: "preview-1",
    display_metadata: { unresolved_todo_count: 2, warning_count: 1 },
  },
  preview_head: {
    version_id: "preview-1",
    version: 1,
    source_digest: "b".repeat(64),
    compile_status: "succeeded" as const,
    preview_head_version_id: "preview-1",
    display_metadata: { unresolved_todo_count: 0, warning_count: 0 },
  },
};

function Harness() {
  return <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <ArtifactPanelProvider workspaceKey="session-1">
      <ArtifactWorkspace variant="chat">
        <main data-testid="conversation-pane"><LatexPaperArtifact descriptor={descriptor} /></main>
      </ArtifactWorkspace>
    </ArtifactPanelProvider>
  </QueryClientProvider>;
}

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(1200);
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/artifacts/artifact-1")) return new Response(JSON.stringify(descriptor));
    if (url.endsWith("/versions/source-1/manifest")) return new Response(JSON.stringify({
      root_document: "main.tex",
      files: [
        { path: "main.tex", media_type: "text/x-tex" },
        { path: "references.bib", media_type: "application/x-bibtex" },
      ],
    }));
    if (url.endsWith("/source/main.tex")) return new Response("\\documentclass{article}");
    return new Response("not found", { status: 404 });
  }));
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Latex paper artifact workspace", () => {
  it("opens a read-only Preview and Files canvas without exposing editing controls", async () => {
    render(<Harness />);

    expect(await screen.findByRole("complementary", { name: "Careful Draft" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Preview" })).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByTitle("Preview of Careful Draft")).toHaveAttribute(
      "src", expect.stringContaining("/versions/preview-1/preview"),
    );
    expect(screen.getByText("Out of date")).toBeVisible();

    screen.getByRole("button", { name: "Files" }).click();
    expect(await screen.findByText("\\documentclass{article}")).toBeVisible();
    expect(screen.queryByRole("button", { name: /save.*compile/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /edit/i })).not.toBeInTheDocument();
  });
});
