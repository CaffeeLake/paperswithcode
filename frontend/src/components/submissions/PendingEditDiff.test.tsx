import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import PendingEditDiff from "@/components/submissions/PendingEditDiff";

describe("PendingEditDiff", () => {
  it("renders external paper submissions for review", () => {
    render(
      <PendingEditDiff
        editType="new_external_paper"
        proposedPayload={{
          title: "A useful external paper",
          source_url: "https://example.com/papers/useful",
          abstract: "A concise summary of the work.",
          authors: ["Ada Lovelace", "Grace Hopper"],
          date_published: "2026-08-10",
        }}
      />,
    );

    expect(screen.getByText("A useful external paper")).toBeInTheDocument();
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("Grace Hopper")).toBeInTheDocument();
    expect(screen.getByText("2026-08-10")).toBeInTheDocument();
    expect(screen.getByText("A concise summary of the work.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "https://example.com/papers/useful" })).toHaveAttribute(
      "href",
      "https://example.com/papers/useful",
    );
    expect(screen.queryByText(/No custom renderer exists/)).not.toBeInTheDocument();
  });
});
