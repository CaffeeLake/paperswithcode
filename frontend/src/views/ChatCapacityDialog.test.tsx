import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatCapacityDialog } from "@/views/ChatView";

describe("ChatCapacityDialog", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-01T20:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("is accessible, focuses Cancel, and closes with Escape", () => {
    const cancel = vi.fn();
    render(
      <ChatCapacityDialog
        retryAt={Date.now() + 5_000}
        onRetry={vi.fn()}
        onCancel={cancel}
      />,
    );

    expect(screen.getByRole("dialog", { name: "All research slots are currently in use" })).toHaveAttribute("aria-modal", "true");
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(cancel).toHaveBeenCalledTimes(1);
  });

  it("never auto-retries and enables only the manual action after the countdown", () => {
    const retry = vi.fn();
    const { unmount } = render(
      <ChatCapacityDialog
        retryAt={Date.now() + 1_000}
        onRetry={retry}
        onCancel={vi.fn()}
      />,
    );
    const button = screen.getByRole("button", { name: "Try again" });

    expect(button).toBeDisabled();
    act(() => vi.advanceTimersByTime(1_000));
    expect(button).toBeEnabled();
    expect(retry).not.toHaveBeenCalled();
    fireEvent.click(button);
    expect(retry).toHaveBeenCalledTimes(1);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
