import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import ExternalSourceEvalBadge from "@/components/ExternalSourceEvalBadge";

function renderBadge(sourceUrl: string) {
  return render(
    <MemoryRouter>
      <ExternalSourceEvalBadge sourceUrl={sourceUrl} />
    </MemoryRouter>,
  );
}

describe("ExternalSourceEvalBadge", () => {
  it("links rewritten paper sources to their internal route", async () => {
    renderBadge("/paper/2412.10117");

    await userEvent.hover(
      screen.getByRole("button", {
        name: "Externally sourced evaluation: Source paper",
      }),
    );

    expect(await screen.findByRole("link", { name: "Source paper" })).toHaveAttribute(
      "href",
      "/paper/2412.10117",
    );
  });

  it("keeps absolute external sources as external links", async () => {
    renderBadge("https://example.com/results");

    await userEvent.hover(
      screen.getByRole("button", {
        name: "Externally sourced evaluation: example.com",
      }),
    );

    expect(await screen.findByRole("link", { name: "example.com" })).toHaveAttribute(
      "href",
      "https://example.com/results",
    );
  });
});
