import React from "react";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { PaperCard } from "@/components";
import type { PaperCardProps } from "@/lib/transform";

const paper: PaperCardProps = {
  id: "2601.18184",
  dbId: "1",
  title: "VibeVoice-ASR Technical Report",
  abstract: "",
  authors: ["Zihliang Peng"],
  tags: [],
  methods: [],
  organizations: [
    {
      name: "Microsoft",
      slug: "microsoft",
      logoUrl: "/api/v1/organizations/microsoft/logo/test.png",
    },
  ],
  citations: 0,
  github: null,
  githubUrl: null,
  project: null,
  date: "Jan 26, 2026",
  publishedIso: "2026-01-26",
  year: 2026,
  thumbnailUrl: null,
  tldr: null,
  version: "v1",
  velocity24h: null,
  hfKind: null,
  hfCount: 0,
  hfUrl: null,
  sotaRanks: [],
};

const renderCard = (showInstitution?: boolean) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PaperCard paper={paper} showInstitution={showInstitution} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

describe("PaperCard organization logos", () => {
  it("links organization logos beside the title by default", () => {
    renderCard();

    const link = screen.getByRole("link", {
      name: "View Microsoft organization",
    });
    expect(link).toHaveAttribute("href", "/orgs/microsoft");
    expect(link.querySelector("img")).toHaveAttribute(
      "src",
      "/api/v1/organizations/microsoft/logo/test.png",
    );
  });

  it("hides organization logos when the feed disables them", () => {
    renderCard(false);

    expect(
      screen.queryByRole("link", { name: "View Microsoft organization" }),
    ).not.toBeInTheDocument();
  });
});
