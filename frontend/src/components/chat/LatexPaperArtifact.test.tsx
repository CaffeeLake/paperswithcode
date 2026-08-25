import { render, screen, waitFor } from "@testing-library/react";
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
    compile_diagnostics: [{
      severity: "error" as const,
      phase: "compiler_error",
      file: "main.tex",
      line: 7,
      message: "Undefined control sequence",
    }],
    repair_attempts_remaining: 3,
    repair_exhausted: false,
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

const savedDescriptor = {
  ...descriptor,
  editing_enabled: true,
  source_head: {
    ...descriptor.source_head,
    version_id: "source-2",
    version: 3,
    compile_status: "succeeded" as const,
    preview_head_version_id: "source-2",
  },
  preview_head: {
    ...descriptor.preview_head,
    version_id: "source-2",
    version: 3,
    compile_status: "succeeded" as const,
    preview_head_version_id: "source-2",
  },
};
let apiDescriptor: typeof descriptor | typeof savedDescriptor;

function Harness({ onAskAiFix }: { onAskAiFix?: (prompt: string) => void } = {}) {
  return <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <ArtifactPanelProvider workspaceKey="session-1" onAskAiFix={onAskAiFix}>
      <ArtifactWorkspace variant="chat">
        <main data-testid="conversation-pane"><LatexPaperArtifact descriptor={descriptor} /></main>
      </ArtifactWorkspace>
    </ArtifactPanelProvider>
  </QueryClientProvider>;
}

beforeEach(() => {
  apiDescriptor = descriptor;
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(1200);
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (init?.method === "POST" && url.endsWith("/save-compile")) return new Response(JSON.stringify(savedDescriptor));
    if (url.endsWith("/artifacts/artifact-1")) return new Response(JSON.stringify(apiDescriptor));
    if (url.endsWith("/versions/source-1/manifest")) return new Response(JSON.stringify({
      root_document: "main.tex",
      files: [
        { path: "main.tex", media_type: "text/x-tex" },
        { path: "references.bib", media_type: "application/x-bibtex" },
      ],
    }));
    if (url.endsWith("/source/main.tex")) return new Response("\\documentclass{article}");
    if (url.endsWith("/source/references.bib")) return new Response("@comment{References}");
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

    expect(screen.getByText(/main\.tex:7.*Undefined control sequence/i)).toBeVisible();

    screen.getByRole("button", { name: "Files" }).click();
    expect(await screen.findByText("\\documentclass{article}")).toBeVisible();
    expect(screen.queryByRole("button", { name: /save.*compile/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /edit/i })).not.toBeInTheDocument();
  });

  it("recovers a browser-local draft and saves it with the checked-out parent", async () => {
    apiDescriptor = { ...descriptor, editing_enabled: true };
    window.localStorage.setItem("pwc:latex-paper-draft:artifact-1", JSON.stringify({
      parentVersionId: "source-1",
      files: {
        "main.tex": "\\documentclass{article}\\begin{document}Local draft\\end{document}",
        "references.bib": "@comment{References}",
      },
    }));
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ArtifactPanelProvider workspaceKey="session-1">
        <ArtifactWorkspace variant="chat"><main><LatexPaperArtifact descriptor={{ ...descriptor, editing_enabled: true }} /></main></ArtifactWorkspace>
      </ArtifactPanelProvider>
    </QueryClientProvider>);

    screen.getByRole("button", { name: "Files" }).click();
    expect(await screen.findByText(/Local draft/)).toBeVisible();
    const save = screen.getByRole("button", { name: /save.*compile/i });
    expect(save).toBeEnabled();
    save.click();

    await waitFor(() => expect(screen.getByRole("button", { name: "Preview" })).toHaveAttribute("aria-pressed", "true"));
    const saveCall = vi.mocked(fetch).mock.calls.find(([url, init]) => String(url).endsWith("/save-compile") && (init as RequestInit).method === "POST");
    expect(saveCall).toBeDefined();
    expect(JSON.parse((saveCall![1] as RequestInit).body as string)).toMatchObject({ expected_parent_version_id: "source-1" });
    expect(window.localStorage.getItem("pwc:latex-paper-draft:artifact-1")).toBeNull();
  });

  it("sends a bounded repair request through the existing chat callback", async () => {
    const onAskAiFix = vi.fn();
    render(<Harness onAskAiFix={onAskAiFix} />);

    (await screen.findByRole("button", { name: "Ask AI to fix" })).click();

    expect(onAskAiFix).toHaveBeenCalledWith(expect.stringContaining("Undefined control sequence"));
    expect(onAskAiFix).toHaveBeenCalledWith(expect.stringContaining("source-1"));
  });
});
