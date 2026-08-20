import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PosterArtifact } from "./PosterArtifact";
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

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState({}, "", "/");
});

describe("PosterArtifact", () => {
  it("auto-opens once when an owner publication becomes ready", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));
    const view = render(<PosterArtifact block={generating} />);
    expect(screen.getByRole("status")).toHaveTextContent("Publishing Posterly preview");

    view.rerender(<PosterArtifact block={ready} />);
    expect(await screen.findByRole("dialog", { name: "Attention poster" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Close poster" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    view.rerender(<PosterArtifact block={{ ...ready, total_bytes: 4097 }} />);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("uses only public snapshot endpoints for a shared poster", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    window.history.replaceState({}, "", "/share/share-1");
    render(<PosterArtifact block={{
      ...ready,
      scope: "public",
      artifact_id: undefined,
      version_id: undefined,
      public_capability: "public-cap-1",
    }} />);

    fireEvent.click(screen.getByRole("button", { name: /Attention poster/u }));
    expect(screen.getByRole("dialog", { name: "Attention poster" })).toBeVisible();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Source" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /PNG/u })).toHaveAttribute(
      "href",
      expect.stringContaining("/api/v1/chat/shares/share-1/artifacts/public-cap-1/download/png"),
    );
  });
});
