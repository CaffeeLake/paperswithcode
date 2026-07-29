import { describe, expect, it } from "vitest";

import { FRAMEWORK_DOMAINS } from "./frameworks";

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
});
