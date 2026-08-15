import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import {
  RecommendedFrameworkLinks,
  TaskBreadcrumb,
} from "@/views/TagBrowseView";

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

describe("TaskBreadcrumb", () => {
  it("shows the task area and parent hierarchy without a Papers root", () => {
    render(
      <MemoryRouter>
        <TaskBreadcrumb
          area={{ id: "6", name: "Audio" }}
          parents={[
            {
              id: "11",
              name: "Speaker Recognition",
              slug: "speaker-recognition",
              level: 0,
            },
          ]}
          task={{
            id: "12",
            name: "Speaker Verification",
            slug: "speaker-verification",
            level: 1,
          }}
        />
      </MemoryRouter>,
    );

    const breadcrumb = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(breadcrumb).toHaveTextContent(
      "Tasks/Audio/Speaker Recognition/Speaker Verification",
    );
    expect(screen.getByRole("link", { name: "Tasks" })).toHaveAttribute(
      "href",
      "/tasks",
    );
    expect(screen.getByRole("link", { name: "Audio" })).toHaveAttribute(
      "href",
      "/tasks#area-audio",
    );
    expect(screen.queryByRole("link", { name: "Papers" })).toBeNull();
  });
});
