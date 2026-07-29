import { describe, expect, it } from "vitest";

import {
  FRAMEWORK_DOMAINS,
  FRAMEWORKS,
  frameworksIntroducedByPaper,
} from "./frameworks";

describe("FRAMEWORK_DOMAINS", () => {
  const frameworks = FRAMEWORK_DOMAINS.flatMap((domain) =>
    domain.categories.flatMap((category) => category.frameworks),
  );

  it("includes the core model libraries", () => {
    expect(frameworks).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          slug: "transformers",
          github: "https://github.com/huggingface/transformers",
        }),
        expect.objectContaining({
          slug: "timm",
          github: "https://github.com/huggingface/pytorch-image-models",
        }),
        expect.objectContaining({
          slug: "lerobot",
          github: "https://github.com/huggingface/lerobot",
        }),
      ]),
    );
  });

  it("uses unique framework slugs", () => {
    const slugs = frameworks.map((framework) => framework.slug);
    expect(new Set(slugs).size).toBe(slugs.length);
  });

  it("exposes the flattened framework catalogue", () => {
    expect(FRAMEWORKS).toEqual(frameworks);
  });
});

describe("frameworksIntroducedByPaper", () => {
  it("finds frameworks by their canonical paper", () => {
    expect(frameworksIntroducedByPaper("2309.06180")).toEqual([
      expect.objectContaining({ slug: "vllm", name: "vLLM" }),
    ]);
  });

  it("normalizes arXiv prefixes and versions", () => {
    expect(frameworksIntroducedByPaper("arXiv:2602.22818v2")).toEqual([
      expect.objectContaining({ slug: "lerobot", name: "LeRobot" }),
    ]);
  });

  it("does not infer a framework when no canonical paper is configured", () => {
    expect(frameworksIntroducedByPaper("2504.16054")).toEqual([]);
    expect(frameworksIntroducedByPaper(null)).toEqual([]);
  });
});
