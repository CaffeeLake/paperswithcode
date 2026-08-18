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
  it("marks only Chat routes for visual brand alignment", () => {
    const trending = render(
      <MemoryRouter initialEntries={["/"]}>
        <Header onOpenSearch={vi.fn()} />
      </MemoryRouter>,
    );
    expect(document.querySelector("header")).toHaveClass("app-header");
    expect(document.querySelector("header")).not.toHaveClass("app-header-chat");

    trending.unmount();
    render(
      <MemoryRouter initialEntries={["/chat"]}>
        <Header onOpenSearch={vi.fn()} />
      </MemoryRouter>,
    );
    expect(document.querySelector("header")).toHaveClass("app-header");
    expect(document.querySelector("header")).toHaveClass("app-header-chat");
  });

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

  it("hides the CLI announcement on PDF reader routes", () => {
    render(
      <MemoryRouter initialEntries={["/pdf/2606.03748"]}>
        <Header onOpenSearch={vi.fn()} />
      </MemoryRouter>,
    );

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
