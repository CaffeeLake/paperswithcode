import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import Header from "@/components/Header";

vi.mock("@/lib/authContext", () => ({
  useAuth: () => ({ user: null, logout: vi.fn() }),
}));

describe("Header", () => {
  it("shows the shared conversation title beside the brand on share pages", () => {
    render(
      <MemoryRouter initialEntries={["/share/example"]}>
        <Header onOpenSearch={vi.fn()} />
      </MemoryRouter>,
    );

    const title = screen.getByRole("heading", { name: "Shared conversation" });
    expect(title).toHaveClass("header-page-title");
    expect(title.closest("header")).toHaveClass("app-header-shared");
  });

  it("does not show the shared conversation title on other pages", () => {
    render(
      <MemoryRouter initialEntries={["/tasks"]}>
        <Header onOpenSearch={vi.fn()} />
      </MemoryRouter>,
    );

    expect(screen.queryByRole("heading", { name: "Shared conversation" })).not.toBeInTheDocument();
  });
});
