import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  CopyToBucketCard,
  buildBucketCopyCommands,
  chunkBucketArtifacts,
  collectBucketArtifacts,
  paperArtifactBucketName,
} from "./CopyToBucketCard";

describe("chunkBucketArtifacts", () => {
  it("keeps large copies within the backend request limit", () => {
    const artifacts = Array.from({ length: 45 }, (_, index) => ({
      kind: "model" as const,
      repo_id: `owner/model-${index}`,
    }));

    const batches = chunkBucketArtifacts(artifacts);

    expect(batches.map((batch) => batch.length)).toEqual([20, 20, 5]);
    expect(batches.flat()).toEqual(artifacts);
  });
});

describe("collectBucketArtifacts", () => {
  it("normalizes and deduplicates linked repositories", () => {
    expect(
      collectBucketArtifacts({
        paperId: "42",
        pdfName: "2601.00001",
        pdfUrl: "https://arxiv.org/pdf/2601.00001v1",
        githubUrls: [
          "https://github.com/huggingface/transformers",
          "https://github.com/huggingface/transformers/",
        ],
        hfModelUrls: ["https://huggingface.co/openai/gpt-oss-20b?ref=paper"],
        hfDatasetUrls: ["https://huggingface.co/datasets/openai/gsm8k"],
        hfSpaceUrls: ["https://huggingface.co/spaces/openai/demo"],
      }).map(({ id, source, destination }) => ({ id, source, destination })),
    ).toEqual([
      {
        id: "pdf",
        source: "https://arxiv.org/pdf/2601.00001v1",
        destination: "paper/2601.00001.pdf",
      },
      {
        id: "model:openai/gpt-oss-20b",
        source: "hf://openai/gpt-oss-20b/",
        destination: "models/openai/gpt-oss-20b/",
      },
      {
        id: "dataset:openai/gsm8k",
        source: "hf://datasets/openai/gsm8k/",
        destination: "datasets/openai/gsm8k/",
      },
      {
        id: "space:openai/demo",
        source: "hf://spaces/openai/demo/",
        destination: "spaces/openai/demo/",
      },
      {
        id: "github:huggingface/transformers",
        source: "https://github.com/huggingface/transformers.git",
        destination: "github/huggingface/transformers/",
      },
    ]);
  });
});

describe("buildBucketCopyCommands", () => {
  it("builds server-side Hub copies and a bounded GitHub checkout", () => {
    const artifacts = collectBucketArtifacts({
      paperId: "42",
      pdfName: "2601.00001",
      pdfUrl: "https://arxiv.org/pdf/2601.00001v1",
      githubUrls: ["https://github.com/huggingface/transformers"],
      hfModelUrls: ["https://huggingface.co/openai/gpt-oss-20b"],
      hfDatasetUrls: [],
      hfSpaceUrls: [],
    });

    const commands = buildBucketCopyCommands("alice/paper-copy", artifacts, {
      create: true,
      isPrivate: true,
    });

    expect(commands).toContain("hf buckets create \"$HF_BUCKET\" --exist-ok --private");
    expect(commands).toContain(
      "hf cp 'hf://openai/gpt-oss-20b/' \"hf://buckets/$HF_BUCKET/models/openai/gpt-oss-20b/\"",
    );
    expect(commands).toContain(
      "curl --fail --location 'https://arxiv.org/pdf/2601.00001v1' --output \"$PWC_PDF\"",
    );
    expect(commands).toContain(
      "hf cp \"$PWC_PDF\" \"hf://buckets/$HF_BUCKET/paper/2601.00001.pdf\"",
    );
    expect(commands).toContain("PWC_COPY_DIR=\"$(mktemp -d)\"");
    expect(commands).toContain(
      "git clone --depth 1 -- 'https://github.com/huggingface/transformers.git'",
    );
    expect(commands).toContain(
      "hf sync \"$PWC_COPY_DIR/github/huggingface/transformers\"",
    );
  });
});

describe("paperArtifactBucketName", () => {
  it("uses the concise title prefix when a paper has a subtitle", () => {
    expect(paperArtifactBucketName("Kimi K3: Open Frontier Intelligence")).toBe(
      "kimi-k3-artifacts",
    );
  });

  it("normalizes punctuation and provides a fallback", () => {
    expect(paperArtifactBucketName("Qwen3 Technical Report")).toBe(
      "qwen3-technical-report-artifacts",
    );
    expect(paperArtifactBucketName("日本語")).toBe("paper-artifacts");
  });
});

describe("CopyToBucketCard", () => {
  it("prefills the suggested signed-in user destination when opened", async () => {
    const user = userEvent.setup();
    render(
      React.createElement(CopyToBucketCard, {
        githubUrls: ["https://github.com/moonshotai/kimi-k3"],
        hfModelUrls: [],
        hfDatasetUrls: [],
        hfSpaceUrls: [],
        paperId: "42",
        pdfName: "42",
        pdfUrl: null,
        isSignedIn: true,
        suggestedBucketId: "nielsr/kimi-k3-artifacts",
      }),
    );

    await user.click(screen.getByRole("button", { name: /copy to bucket/i }));

    expect(screen.getByLabelText("Bucket name")).toHaveValue(
      "nielsr/kimi-k3-artifacts",
    );
  });
});
