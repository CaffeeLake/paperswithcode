import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EditOrganizationsDialog } from "./EditOrganizationsDialog";

const { getOrganizations, updatePaperOrganizations } = vi.hoisted(() => ({
  getOrganizations: vi.fn(),
  updatePaperOrganizations: vi.fn(),
}));

vi.mock("@/lib/api/catalog", () => ({
  catalogApi: { organizations: getOrganizations },
}));

vi.mock("@/lib/api/papers", () => ({
  papersApi: { updateOrganizations: updatePaperOrganizations },
}));

const organizations = {
  count: 3,
  results: [
    { id: "1", name: "NVIDIA", slug: "nvidia", is_featured: true },
    { id: "2", name: "ByteDance Seed", slug: "bytedance-seed", is_featured: true },
    { id: "3", name: "Google DeepMind", slug: "google-deepmind", is_featured: true },
  ],
};

function renderDialog(initialOrganizationIds: number[] = []) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <EditOrganizationsDialog
        open
        onOpenChange={vi.fn()}
        paperId="42"
        initialOrganizationIds={initialOrganizationIds}
        submitMode="direct"
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  getOrganizations.mockReset();
  getOrganizations.mockResolvedValue(organizations);
  updatePaperOrganizations.mockReset();
  updatePaperOrganizations.mockResolvedValue(undefined);
});

describe("EditOrganizationsDialog", () => {
  it("filters organizations by name without losing hidden selections", async () => {
    const user = userEvent.setup();
    renderDialog([1]);

    expect(await screen.findByText("NVIDIA")).toBeInTheDocument();
    await user.type(screen.getByRole("searchbox", { name: "Search organizations" }), "seed");

    expect(screen.getByText("ByteDance Seed")).toBeInTheDocument();
    expect(screen.queryByText("NVIDIA")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Clear organization search" }));
    expect(screen.getByRole("checkbox", { name: "NVIDIA" })).toBeChecked();
  });

  it("shows an empty state when the search has no matches", async () => {
    const user = userEvent.setup();
    renderDialog();

    await screen.findByText("NVIDIA");
    await user.type(screen.getByRole("searchbox", { name: "Search organizations" }), "missing");

    expect(screen.getByText('No organizations found matching "missing"')).toBeInTheDocument();
  });
});
