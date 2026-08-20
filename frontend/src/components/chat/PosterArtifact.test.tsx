import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ArtifactWorkspace, clampArtifactPercent } from "./ArtifactWorkspace";
import { PosterArtifact } from "./PosterArtifact";
import { ArtifactPanelProvider } from "./useArtifactPanel";
import type { ArtifactBlock } from "@/lib/chat";

const generating: ArtifactBlock = {
  kind: "artifact",
  schema_version: 1,
  scope: "owner",
  publication_id: "poster-1",
  identifier: "attention-poster",
  artifact_kind: "posterly",
  title: "Attention poster",
  status: "generating",
};

const ready: ArtifactBlock = {
  ...generating,
  artifact_id: "artifact-1",
  version_id: "version-1",
  version: 1,
  status: "ready",
  preview_mime: "image/png",
  source_language: "html",
  gate_status: "passed",
  total_bytes: 4096,
};

function Harness({
  block,
  workspaceKey = "session-1",
  publicInitial = false,
}: {
  block: ArtifactBlock;
  workspaceKey?: string;
  publicInitial?: boolean;
}) {
  return <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <ArtifactPanelProvider workspaceKey={workspaceKey} autoOpenOnMount={publicInitial}>
      <ArtifactWorkspace variant={publicInitial ? "shared" : "chat"}>
        <main data-testid="conversation-pane"><PosterArtifact block={block} /></main>
      </ArtifactWorkspace>
    </ArtifactPanelProvider>
  </QueryClientProvider>;
}

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(1200);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.history.replaceState({}, "", "/");
});

describe("Poster artifact workspace", () => {
  it("auto-opens the first ready owner version once in a persistent desktop split", async () => {
    const view = render(<Harness block={generating} />);
    expect(screen.getByRole("status")).toHaveTextContent("Publishing Posterly preview");

    view.rerender(<Harness block={ready} />);
    expect(await screen.findByRole("complementary", { name: "Attention poster" })).toBeVisible();
    expect(screen.getByTestId("conversation-pane").closest("[data-artifact-layout]"))
      .toHaveAttribute("data-artifact-layout", "split");
    expect(screen.getByRole("separator", { name: /conversation and poster/u }))
      .toHaveAttribute("aria-valuenow", "55");

    fireEvent.click(screen.getByRole("button", { name: "Close poster" }));
    expect(screen.queryByTestId("artifact-panel")).not.toBeInTheDocument();
    view.rerender(<Harness block={{ ...ready, total_bytes: 4097 }} />);
    await waitFor(() => expect(screen.queryByTestId("artifact-panel")).not.toBeInTheDocument());
  });

  it("keeps card selection open across conversation updates and restores it after close", async () => {
    const view = render(<Harness block={ready} />);
    const card = screen.getByRole("button", { name: /Attention poster/u });
    fireEvent.click(card);
    expect(await screen.findByRole("complementary", { name: "Attention poster" })).toBeVisible();
    view.rerender(<Harness block={{ ...ready, total_bytes: 5000 }} />);
    expect(screen.getByRole("complementary", { name: "Attention poster" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Close poster" }));
    fireEvent.click(screen.getByRole("button", { name: /Attention poster/u }));
    expect(screen.getByRole("complementary", { name: "Attention poster" })).toBeVisible();
  });

  it("resets selection safely when the chat session changes", async () => {
    const view = render(<Harness block={ready} workspaceKey="session-1" />);
    fireEvent.click(screen.getByRole("button", { name: /Attention poster/u }));
    expect(await screen.findByTestId("artifact-panel")).toBeVisible();
    view.rerender(<Harness block={ready} workspaceKey="session-2" />);
    await waitFor(() => expect(screen.queryByTestId("artifact-panel")).not.toBeInTheDocument());
  });

  it("bounds desktop resizing and supports keyboard resize and reset", async () => {
    expect(clampArtifactPercent(1200, 90, 360, 360)).toBe(70);
    expect(clampArtifactPercent(1200, 10, 360, 360)).toBe(30);
    render(<Harness block={ready} />);
    fireEvent.click(screen.getByRole("button", { name: /Attention poster/u }));
    const separator = await screen.findByRole("separator", { name: /conversation and poster/u });
    fireEvent.keyDown(separator, { key: "End" });
    expect(separator).toHaveAttribute("aria-valuenow", "70");
    fireEvent.doubleClick(separator);
    expect(separator).toHaveAttribute("aria-valuenow", "55");
  });

  it("uses an accessible full-screen dialog at mobile width with Escape and focus return", async () => {
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(500);
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    render(<Harness block={ready} />);
    const card = screen.getByRole("button", { name: /Attention poster/u });
    fireEvent.click(card);
    expect(await screen.findByRole("dialog", { name: "Attention poster" })).toHaveAttribute("aria-modal", "true");
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(card).toHaveFocus());
  });

  it("opens a public poster immediately and never requests owner artifact APIs", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    window.history.replaceState({}, "", "/share/share-1");
    render(<Harness publicInitial block={{
      ...ready,
      scope: "public",
      artifact_id: undefined,
      version_id: undefined,
      public_capability: "public-cap-1",
    }} />);

    expect(await screen.findByRole("complementary", { name: "Attention poster" })).toBeVisible();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Source" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /PNG/u })).toHaveAttribute(
      "href",
      expect.stringContaining("/api/v1/chat/shares/share-1/artifacts/public-cap-1/download/png"),
    );
  });
});
