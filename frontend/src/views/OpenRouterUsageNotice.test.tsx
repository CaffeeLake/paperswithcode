import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OPENROUTER_USAGE_QUERY_KEY } from "@/lib/openrouter";
import { OpenRouterUsageNotice } from "@/views/ChatView";

describe("OpenRouterUsageNotice", () => {
  it("moves non-admin staging users to production without advertising shared credit", () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    queryClient.setQueryData(OPENROUTER_USAGE_QUERY_KEY, {
      used_percent: 12,
      remaining_percent: 88,
      resets_at: "2026-09-01T00:00:00Z",
      available: false,
      unavailable_reason: "staging_funding_disabled",
      production_chat_url: "https://paperswithcode.co/chat",
      as_of: "2026-08-14T12:00:00Z",
    });

    render(
      <QueryClientProvider client={queryClient}>
        <OpenRouterUsageNotice enabled fallbackEnabled={false} />
      </QueryClientProvider>,
    );

    expect(screen.getByText("Chat is now live on paperswithcode.co")).toBeVisible();
    expect(screen.getByRole("link", { name: "Continue on production" })).toHaveAttribute(
      "href",
      "https://paperswithcode.co/chat",
    );
    expect(screen.queryByText(/88% left/)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Connect your own key/ })).not.toBeInTheDocument();
  });
});
