import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PaperFeedFilters } from "@/components/PaperFeedFilters";

describe("PaperFeedFilters", () => {
  it("renders independent code and Hugging Face artifact checkboxes", async () => {
    const onHasCodeChange = vi.fn();
    const onHasHfArtifactsChange = vi.fn();
    const user = userEvent.setup();

    render(
      <PaperFeedFilters
        hasCode={false}
        hasHfArtifacts
        onHasCodeChange={onHasCodeChange}
        onHasHfArtifactsChange={onHasHfArtifactsChange}
      />,
    );

    const hasCode = screen.getByRole("checkbox", { name: "Has code" });
    const hasHfArtifacts = screen.getByRole("checkbox", {
      name: "Has HF artifacts",
    });

    expect(hasCode).not.toBeChecked();
    expect(hasHfArtifacts).toBeChecked();

    await user.click(hasCode);
    await user.click(hasHfArtifacts);

    expect(onHasCodeChange).toHaveBeenCalledWith(true);
    expect(onHasHfArtifactsChange).toHaveBeenCalledWith(false);
  });
});
