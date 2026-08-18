import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import Header from "@/components/Header";

vi.mock("@/lib/apiUrl", () => ({
  isAuthDisabled: () => false,
  isChatEnabled: () => true,
}));

vi.mock("@/lib/authContext", () => ({
  useAuth: () => ({ user: null, logout: vi.fn() }),
}));

vi.mock("@/components/HfSignInButton", () => ({
  default: () => <button type="button">Sign in</button>,
}));

describe("Header navigation", () => {
  it("places Chat immediately after Trending in desktop and mobile navigation", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Header onOpenSearch={vi.fn()} />
      </MemoryRouter>,
    );

    const desktopLabels = within(screen.getByRole("navigation"))
      .getAllByRole("link")
      .map((link) => link.textContent);
    expect(desktopLabels.slice(0, 3)).toEqual([
      "Trending",
      "Chat",
      "Browse state-of-the-art",
    ]);

    await user.click(screen.getByRole("button", { name: "Open menu" }));
    const mobilePanel = document.querySelector(".mobile-nav-panel");
    expect(mobilePanel).not.toBeNull();
    const mobileLabels = within(mobilePanel as HTMLElement)
      .getAllByRole("link")
      .map((link) => link.textContent);
    expect(mobileLabels.slice(0, 3)).toEqual([
      "Trending",
      "Chat",
      "Browse state-of-the-art",
    ]);
  });
});
