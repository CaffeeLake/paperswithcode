import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PaperDateFilter } from "@/components/PaperDateFilter";

describe("PaperDateFilter", () => {
  it("applies an inclusive range from the two-month calendar", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();

    render(<PaperDateFilter currentDate="2026-08-21" onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: "Select a range" }));

    const dialog = screen.getByRole("dialog", { name: "Select a date range" });
    expect(within(dialog).getByText("August 2026")).toBeInTheDocument();
    expect(within(dialog).getByText("September 2026")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "2026-08-22" })).toBeDisabled();

    await user.click(within(dialog).getByRole("button", { name: "2026-08-03" }));
    await user.click(within(dialog).getByRole("button", { name: "2026-08-10" }));
    await user.click(within(dialog).getByRole("button", { name: "Apply" }));

    expect(onChange).toHaveBeenCalledWith({
      startDate: "2026-08-03",
      endDate: "2026-08-10",
    });
  });

  it("supports same-day ranges and resets the start for an earlier second click", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();

    render(<PaperDateFilter currentDate="2026-08-21" onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: "Select a range" }));
    const dialog = screen.getByRole("dialog", { name: "Select a date range" });

    await user.click(within(dialog).getByRole("button", { name: "2026-08-10" }));
    await user.click(within(dialog).getByRole("button", { name: "2026-08-03" }));
    expect(within(dialog).getByRole("button", { name: "Apply" })).toBeDisabled();

    await user.click(within(dialog).getByRole("button", { name: "2026-08-03" }));
    await user.click(within(dialog).getByRole("button", { name: "Apply" }));

    expect(onChange).toHaveBeenCalledWith({
      startDate: "2026-08-03",
      endDate: "2026-08-03",
    });
  });

  it("maps presets to explicit UTC dates and clears a custom range", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();

    render(
      <PaperDateFilter
        startDate="2026-08-03"
        endDate="2026-08-10"
        currentDate="2026-08-21"
        onChange={onChange}
      />,
    );

    expect(screen.getByRole("button", { name: "Change date range" })).toHaveTextContent(
      "Aug 3–10, 2026",
    );
    await user.click(screen.getByRole("button", { name: "This Week" }));
    expect(onChange).toHaveBeenLastCalledWith({
      startDate: "2026-08-17",
      endDate: "2026-08-21",
    });

    await user.click(screen.getByRole("button", { name: "Change date range" }));
    await user.click(screen.getByRole("button", { name: "Clear range" }));
    expect(onChange).toHaveBeenLastCalledWith({});
  });
});
