import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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
    vi.stubEnv("VITE_CHAT_ENABLED", "1");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("lets a connected user select an organization billing account", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes("/chat/usage")) return new Response(JSON.stringify({
        used_percent: 4,
        remaining_percent: 96,
        resets_at: "2026-09-01T00:00:00Z",
        available: true,
        as_of: "2026-08-02T00:00:00Z",
      }), { status: 200, headers: { "Content-Type": "application/json" } });
      if (url.includes("/chat/openrouter-key")) return new Response(JSON.stringify({
        connected: false,
        verified_at: null,
        fallback_enabled: false,
      }), { status: 200, headers: { "Content-Type": "application/json" } });
      const body = init?.method === "PATCH" ? {
        ...personalStatus,
        account_type: "Organization",
        monthly_credits_usd: null,
        bill_to: "huggingface",
      } : personalStatus;
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

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
    expect(screen.getByText("Organization · huggingface")).toBeVisible();
    expect(screen.queryByText(/chat starts \/ minute/)).not.toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /monthly Hugging Face inference credit/ })).not.toBeInTheDocument();
  });

  it("uses OAuth authorization instead of asking for a manual token", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/me/inference-billing")) return new Response(JSON.stringify({
        ...personalStatus,
        connected: false,
        account_type: null,
        monthly_credits_usd: null,
        organizations: [],
      }), { status: 200, headers: { "Content-Type": "application/json" } });
      if (url.includes("/chat/usage")) return new Response(JSON.stringify({
        used_percent: 4, remaining_percent: 96,
        resets_at: "2026-09-01T00:00:00Z", available: true,
        as_of: "2026-08-02T00:00:00Z",
      }), { status: 200, headers: { "Content-Type": "application/json" } });
      return new Response(JSON.stringify({
        connected: false, verified_at: null, fallback_enabled: false,
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    });

    renderSettings();

    expect(
      await screen.findByRole("button", { name: "Sign in with Hugging Face" }),
    ).toHaveTextContent("Authorize with Hugging Face");
    expect(screen.queryByLabelText("Hugging Face token")).not.toBeInTheDocument();
    expect(screen.getByText(/Reconnect with Hugging Face/)).toBeVisible();
  });

  it("renders exactly two billing providers and exposes percentage-only OpenRouter usage", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      const payload = url.includes("/me/inference-billing")
        ? personalStatus
        : url.includes("/chat/usage")
          ? {
              used_percent: 4,
              remaining_percent: 96,
              resets_at: "2026-09-01T00:00:00Z",
              available: true,
              as_of: "2026-08-02T00:00:00Z",
            }
          : {
              connected: true,
              verified_at: "2026-08-02T12:00:00Z",
              fallback_enabled: false,
            };
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    renderSettings();

    expect(await screen.findByRole("heading", { name: "Inference Providers" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "OpenRouter" })).toBeVisible();
    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(2);
    expect(await screen.findByText("96% left")).toBeVisible();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "96");
    expect(screen.getByText(/pay-as-you-go billing applies once it is depleted/)).toBeVisible();
    expect(screen.getByText(/stored securely using AES-256 encryption/)).toBeVisible();
    expect(screen.queryByText(/\$1|dollar|USD/i)).not.toBeInTheDocument();
    expect(screen.getByRole("switch", { name: /Use my OpenRouter key/ })).not.toBeChecked();
  });
});

describe("SettingsView production boundary", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubEnv("VITE_CHAT_ENABLED", "0");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("hides chat usage and billing without requesting chat billing data", () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");

    renderSettings();

    expect(screen.queryByRole("heading", { name: "Chat usage & billing" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Inference Providers" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "OpenRouter" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Appearance" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Evaluations" })).toBeVisible();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
