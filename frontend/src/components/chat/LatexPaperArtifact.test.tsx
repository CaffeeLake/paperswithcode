import { render, screen, waitFor, within } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
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
const restoredDescriptor = {
  ...savedDescriptor,
  source_head: { ...savedDescriptor.source_head, version_id: "source-4", version: 4 },
  preview_head: { ...savedDescriptor.preview_head, version_id: "source-4", version: 4 },
};
const history = {
  items: [
    {
      ...savedDescriptor.source_head,
      created_at: "2026-08-25T12:00:00Z",
      actor_type: "ai" as const,
      parent_version_id: "source-1",
      provenance: {
        action: "ai_repair" as const,
        model_identity: "GPT Test",
        changed_files: ["main.tex"],
        reference_changes: ["Updated one citation."],
      },
    },
    {
      ...descriptor.source_head,
      actor_type: "human" as const,
      provenance: { action: "human_save" as const, changed_files: [], reference_changes: [] },
    },
  ],
  next_cursor: null,
};
let apiDescriptor: typeof descriptor | typeof savedDescriptor | typeof restoredDescriptor;

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
    if (init?.method === "POST" && url.endsWith("/versions/restore")) {
      apiDescriptor = restoredDescriptor;
      return new Response(JSON.stringify(restoredDescriptor));
    }
    if (url.includes("/versions?limit=20")) return new Response(JSON.stringify(history));
    if (url.endsWith("/artifacts/artifact-1")) return new Response(JSON.stringify(apiDescriptor));
    if (/\/versions\/(?:source-1|source-2|source-4)\/manifest$/.test(url)) return new Response(JSON.stringify({
      root_document: "main.tex",
      files: [
        { path: "main.tex", media_type: "text/x-tex" },
        { path: "references.bib", media_type: "application/x-bibtex" },
      ],
    }));
    if (url.endsWith("/source/main.tex")) return new Response(apiDescriptor === restoredDescriptor ? "Restored source" : "\\documentclass{article}");
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

  it("browses bounded version provenance and restores a historical snapshot as a new head", async () => {
    apiDescriptor = savedDescriptor;
    render(<Harness />);

    screen.getByRole("button", { name: "Version history" }).click();
    const repairEntry = (await screen.findByText("AI repair · GPT Test")).closest("article")!;
    expect(within(repairEntry).getByText("Changed: main.tex")).toBeVisible();
    expect(within(repairEntry).getByText("Parent v2")).toBeVisible();
    expect(within(repairEntry).getByText("2026-08-25T12:00:00Z")).toBeVisible();
    expect(within(repairEntry).getByText("Updated one citation.")).toBeVisible();
    screen.getByRole("button", { name: "Restore version 2" }).click();

    await waitFor(() => expect(screen.getByText("Source v4 · succeeded")).toBeVisible());
    const restoreCall = vi.mocked(fetch).mock.calls.find(([url, init]) => (
      String(url).endsWith("/versions/restore") && (init as RequestInit).method === "POST"
    ));
    expect(JSON.parse((restoreCall![1] as RequestInit).body as string)).toEqual({
      source_version_id: "source-1", expected_parent_version_id: "source-2",
    });
    screen.getByRole("button", { name: "Files" }).click();
    expect(await screen.findByText("Restored source")).toBeVisible();
  });

  it("uploads an approved figure through the owner-only paper endpoint", async () => {
    apiDescriptor = { ...descriptor, editing_enabled: true };
    render(<Harness />);
    screen.getByRole("button", { name: "Files" }).click();

    const input = await screen.findByLabelText("Upload figure");
    fireEvent.change(input, {
      target: { files: [new File([new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10])], "result.png", { type: "image/png" })] },
    });

    await waitFor(() => {
      const upload = vi.mocked(fetch).mock.calls.find(([url, init]) => String(url).endsWith("/figures") && (init as RequestInit).method === "POST");
      expect(upload).toBeDefined();
      expect((upload![1] as RequestInit).body).toBeInstanceOf(FormData);
    });
  });
});
