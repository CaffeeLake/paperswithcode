import { describe, expect, it } from "vitest";

import {
  buildBucketCopyCommands,
  collectBucketArtifacts,
} from "./CopyToBucketCard";

describe("collectBucketArtifacts", () => {
  it("normalizes and deduplicates linked repositories", () => {
    expect(
      collectBucketArtifacts({
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
    expect(commands).toContain("PWC_COPY_DIR=\"$(mktemp -d)\"");
    expect(commands).toContain(
      "git clone --depth 1 -- 'https://github.com/huggingface/transformers.git'",
    );
    expect(commands).toContain(
      "hf sync \"$PWC_COPY_DIR/github/huggingface/transformers\"",
    );
  });
});
