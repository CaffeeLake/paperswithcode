import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

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

afterEach(() => vi.restoreAllMocks());

describe("Header navigation", () => {
  it("places Chat immediately after Trending in desktop and mobile navigation", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Header onOpenSearch={vi.fn()} />
      </MemoryRouter>,
    );

    const desktopLinks = within(screen.getByRole("navigation")).getAllByRole("link");
    expect(desktopLinks[0]).toHaveAccessibleName("Trending");
    expect(desktopLinks[1]).toHaveAccessibleName("Chat");
    expect(desktopLinks[2]).toHaveAccessibleName("Browse state-of-the-art");
    expect(within(desktopLinks[1]).getByText("New")).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent(
      "New: Papers with Code CLI and Skill now available",
    );
    expect(within(screen.getByRole("status")).queryByRole("link", { name: "chat" }))
      .not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Open menu" }));
    const mobilePanel = document.querySelector(".mobile-nav-panel");
    expect(mobilePanel).not.toBeNull();
    const mobileLinks = within(mobilePanel as HTMLElement).getAllByRole("link");
    expect(mobileLinks[0]).toHaveAccessibleName("Trending");
    expect(mobileLinks[1]).toHaveAccessibleName("Chat");
    expect(mobileLinks[2]).toHaveAccessibleName("Browse state-of-the-art");
    expect(within(mobileLinks[1]).getByText("New")).toBeVisible();
  });
  it("slides one shared indicator to the active desktop tab", async () => {
    vi.spyOn(HTMLElement.prototype, "offsetLeft", "get")
      .mockImplementation(function getOffsetLeft() {
        return this.textContent?.includes("Chat") ? 96 : 0;
      });
    vi.spyOn(HTMLElement.prototype, "offsetWidth", "get")
      .mockImplementation(function getOffsetWidth() {
        return this.classList.contains("nav-item") ? 64 : 0;
      });
    const user = userEvent.setup();

    const { container } = render(
      <MemoryRouter initialEntries={["/"]}>
        <Header onOpenSearch={vi.fn()} />
      </MemoryRouter>,
    );
    const indicator = container.querySelector<HTMLElement>(".nav-indicator");
    expect(indicator).not.toBeNull();
    await waitFor(() => expect(indicator).toHaveStyle({
      transform: "translateX(0px)",
      width: "64px",
    }));

    await user.click(within(screen.getByRole("navigation")).getByRole("link", { name: "Chat" }));
    await waitFor(() => expect(indicator).toHaveStyle({
      transform: "translateX(96px)",
      width: "64px",
    }));
    expect(container.querySelectorAll(".nav-indicator")).toHaveLength(1);
  });
});
