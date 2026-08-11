import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SettingsView from "@/views/SettingsView";

const mockAuth = vi.hoisted(() => ({
  state: {
    user: { username: "nielsr", hf_subject: "hf-user-1" } as {
      username: string;
      hf_subject: string;
    } | null,
    isLoading: false,
  },
}));
const mockCanPersist = vi.hoisted(() => ({ value: true }));

vi.mock("next-themes", () => ({
  useTheme: () => ({ theme: "system", setTheme: vi.fn() }),
}));

vi.mock("@/lib/authContext", () => ({
  useAuth: () => mockAuth.state,
}));

vi.mock("@/lib/preferencesContext", () => ({
  usePreferences: () => ({
    preferences: { hideClosedSourceEvals: false },
    setHideClosedSourceEvals: vi.fn(),
    canPersist: mockCanPersist.value,
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
    vi.stubEnv("MODE", "staging");
    mockAuth.state = {
      user: { username: "nielsr", hf_subject: "hf-user-1" },
      isLoading: false,
    };
    mockCanPersist.value = true;
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("lets a connected user select an organization billing account", async () => {
    vi.stubEnv("MODE", "production");
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
    vi.stubEnv("MODE", "production");
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
    ).toHaveTextContent("Re-sign in with Hugging Face");
    expect(screen.queryByLabelText("Hugging Face token")).not.toBeInTheDocument();
    expect(screen.getByText(/Reconnect with Hugging Face/)).toBeVisible();
  });

  it("shows only OpenRouter on staging and exposes percentage-only usage", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock.mockImplementation(async (input) => {
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

    expect(await screen.findByRole("heading", { name: "OpenRouter" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Inference Providers" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(1);
    expect(await screen.findByText("96% left")).toBeVisible();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "96");
    expect(screen.getByText(/stored securely using AES-256 encryption/)).toBeVisible();
    expect(screen.queryByText(/\$\d|dollar|USD/i)).not.toBeInTheDocument();
    expect(screen.getByRole("switch", { name: /Use my OpenRouter key/ })).not.toBeChecked();
    expect(fetchMock.mock.calls.some(([input]) => (
      String(input).includes("/me/inference-billing")
    ))).toBe(false);
  });

  it("does not present personal allowance as usable when shared credits are depleted", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      const payload = url.includes("/me/inference-billing")
        ? personalStatus
        : url.includes("/chat/usage")
          ? {
              used_percent: 57,
              remaining_percent: 43,
              resets_at: "2026-09-01T00:00:00Z",
              available: false,
              unavailable_reason: "shared_credits_exhausted",
              as_of: "2026-08-04T17:43:39Z",
            }
          : {
              connected: false,
              verified_at: null,
              fallback_enabled: false,
            };
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    renderSettings();

    expect(await screen.findByText("Unavailable")).toBeVisible();
    expect(screen.getByText(/shared OpenRouter credits are currently unavailable/i)).toHaveTextContent(
      "43% of your personal allowance remains",
    );
    expect(screen.queryByText("43% left")).not.toBeInTheDocument();
  });

  it("offers a direct security refresh when connecting a key needs fresh auth", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes("/me/inference-billing")) {
        return new Response(JSON.stringify(personalStatus), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes("/chat/usage")) {
        return new Response(JSON.stringify({
          used_percent: 57,
          remaining_percent: 43,
          resets_at: "2026-09-01T00:00:00Z",
          available: false,
          unavailable_reason: "shared_credits_exhausted",
          as_of: "2026-08-04T17:43:39Z",
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (init?.method === "PUT") {
        return new Response(JSON.stringify({
          detail: {
            code: "fresh_auth_required",
            message: "For security, refresh your Hugging Face sign-in before changing your OpenRouter key.",
          },
        }), { status: 401, statusText: "Unauthorized", headers: { "Content-Type": "application/json" } });
      }
      return new Response(JSON.stringify({
        connected: false,
        verified_at: null,
        fallback_enabled: false,
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    });

    renderSettings();
    const keyInput = await screen.findByLabelText("OpenRouter API key");
    await userEvent.type(keyInput, "sk-or-test");
    await userEvent.click(screen.getByRole("button", { name: "Connect key" }));

    expect(await screen.findByText(/account is signed in/i)).toBeVisible();
    expect(screen.getByText("Re-authenticate with Hugging Face").closest("button")).toBeVisible();
  });

  it("does not flash the sign-in prompt while the account is loading", () => {
    mockAuth.state = { user: null, isLoading: true };
    mockCanPersist.value = false;
    const fetchMock = vi.spyOn(globalThis, "fetch");

    renderSettings();

    expect(screen.getByRole("status")).toHaveTextContent("Checking account…");
    expect(screen.queryByText(/Sign in to connect your Hugging Face account/)).not.toBeInTheDocument();
    expect(screen.queryByText(/You are browsing as a guest/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign in with Hugging Face" })).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the sign-in prompt after authentication resolves signed out", () => {
    mockAuth.state = { user: null, isLoading: false };
    mockCanPersist.value = false;

    renderSettings();

    expect(screen.getByText(/Sign in to use the Papers With Code-funded OpenRouter allowance/)).toBeVisible();
    expect(screen.getByText(/You are browsing as a guest/)).toBeVisible();
    expect(screen.getAllByRole("button", { name: "Sign in with Hugging Face" })).toHaveLength(2);
  });
});

describe("SettingsView production boundary", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubEnv("VITE_CHAT_ENABLED", "0");
    mockAuth.state = {
      user: { username: "nielsr", hf_subject: "hf-user-1" },
      isLoading: false,
    };
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

  it("shows Hugging Face and retention policy but no OpenRouter when production chat is previewed", async () => {
    vi.stubEnv("VITE_CHAT_ENABLED", "1");
    vi.stubEnv("MODE", "production");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(personalStatus), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    renderSettings();

    expect(await screen.findByRole("heading", { name: "Inference Providers" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "OpenRouter" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Monthly OpenRouter usage/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText("OpenRouter API key")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Chat privacy & retention" })).toBeVisible();
    expect(screen.getByText(/retained until you delete them/i)).toBeVisible();
    expect(screen.getByText(/no dedicated private-chat export format/i)).toBeVisible();
    expect(screen.getByText(/Archiving.*does not delete/i)).toBeVisible();
  });
});
