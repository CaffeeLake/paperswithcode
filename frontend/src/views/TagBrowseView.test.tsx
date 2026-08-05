import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { RecommendedFrameworkLinks } from "@/views/TagBrowseView";

describe("RecommendedFrameworkLinks", () => {
  it("links recommendations to their internal framework paper feeds", () => {
    render(
      <MemoryRouter>
        <RecommendedFrameworkLinks
          frameworks={[{
            id: "10",
            framework_id: "30",
            framework_slug: "transformers",
            framework_name: "Transformers",
            url: "https://github.com/huggingface/transformers",
            owner: "huggingface",
            name: "transformers",
            num_stars: 150_000,
          }]}
        />
      </MemoryRouter>,
    );

    const link = screen.getByRole("link", { name: /Transformers/ });
    expect(link).toHaveAttribute("href", "/papers?framework=transformers");
    expect(link).not.toHaveAttribute("target");
  });
});
