import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsView from "@/views/SettingsView";

vi.mock("next-themes", () => ({
  useTheme: () => ({ theme: "system", setTheme: vi.fn() }),
}));

vi.mock("@/lib/authContext", () => ({
  useAuth: () => ({
    user: { username: "nielsr", hf_subject: "hf-user-1" },
  }),
}));

vi.mock("@/lib/preferencesContext", () => ({
  usePreferences: () => ({
    preferences: { hideClosedSourceEvals: false },
    setHideClosedSourceEvals: vi.fn(),
    canPersist: true,
  }),
}));

const personalStatus = {
  connected: true,
  account_type: "PRO",
  monthly_credits_usd: 2,
  pay_as_you_go: true,
  usage_url: "https://huggingface.co/settings/inference-providers",
  token_url: "https://huggingface.co/settings/tokens/new",
  bill_to: null,
  organizations: [
    { name: "huggingface", display_name: "Hugging Face" },
  ],
};

const renderSettings = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <SettingsView />
    </QueryClientProvider>,
  );
};

describe("SettingsView organization billing", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("lets a connected user select an organization billing account", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock
      .mockResolvedValueOnce(
        new Response(JSON.stringify(personalStatus), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ...personalStatus,
            account_type: "Organization",
            monthly_credits_usd: null,
            bill_to: "huggingface",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );

    renderSettings();
    const selector = await screen.findByRole("combobox", {
      name: "Bill chat usage to",
    });
    expect(selector).toHaveValue("");
    expect(screen.getByRole("option", { name: "Hugging Face (huggingface)" })).toBeVisible();

    await userEvent.selectOptions(selector, "huggingface");

    await waitFor(() => expect(selector).toHaveValue("huggingface"));
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining("/api/v1/me/inference-billing"),
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ bill_to: "huggingface" }),
      }),
    );
    expect(screen.getByText("Hugging Face organization · huggingface")).toBeVisible();
    expect(screen.queryByText(/chat starts \/ minute/)).not.toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /monthly Hugging Face inference credit/ })).not.toBeInTheDocument();
  });

  it("uses OAuth authorization instead of asking for a manual token", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          ...personalStatus,
          connected: false,
          account_type: null,
          monthly_credits_usd: null,
          organizations: [],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    renderSettings();

    expect(
      await screen.findByRole("button", { name: "Sign in with Hugging Face" }),
    ).toHaveTextContent("Authorize with Hugging Face");
    expect(screen.queryByLabelText("Hugging Face token")).not.toBeInTheDocument();
    expect(screen.getByText(/No manually created token is needed/)).toBeVisible();
  });
});
