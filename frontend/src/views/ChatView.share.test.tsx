import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  busy: false,
  authUser: { username: "owner", hf_user_id: "hf-owner" },
  messages: [{
    id: "user-1",
    role: "user" as const,
    text: "Question",
    revision: 1,
    status: "complete",
  }],
  load: vi.fn(),
  reset: vi.fn(),
  send: vi.fn(() => true),
  stop: vi.fn(),
  toggleBlock: vi.fn(),
  editAndResend: vi.fn(() => true),
  getSession: vi.fn(),
  listSessions: vi.fn(),
  getChatModels: vi.fn(),
  createShare: vi.fn(),
  toast: vi.fn(),
  clipboardWrite: vi.fn(),
  hfLoginUrl: vi.fn(() => window.location.href),
  chatOptions: null as {
    onSessionId: (id: string) => void;
    onTitle: (title: string) => void;
    onSettled: (id: string | null) => void;
  } | null,
}));

vi.mock("@/hooks/useChat", () => ({
  useChat: (options: NonNullable<typeof mocks.chatOptions>) => {
    mocks.chatOptions = options;
    return {
      busy: mocks.busy,
      messages: mocks.messages,
      papers: {},
      sessionError: "",
      load: mocks.load,
      reset: mocks.reset,
      send: mocks.send,
      stop: mocks.stop,
      toggleBlock: mocks.toggleBlock,
      editAndResend: mocks.editAndResend,
    };
  },
}));
vi.mock("@/lib/authContext", () => ({
  useAuth: () => ({
    user: mocks.authUser,
    isLoading: false,
  }),
}));
vi.mock("@/components/ui/use-toast", () => ({
  useToast: () => ({ toast: mocks.toast }),
}));
vi.mock("@/components/HfSignInButton", () => ({
  hfLoginUrl: mocks.hfLoginUrl,
}));
vi.mock("@/lib/chatSessions", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/chatSessions")>();
  return {
    ...original,
    getSession: mocks.getSession,
    listSessions: mocks.listSessions,
    getChatModels: mocks.getChatModels,
    createOrRefreshShare: mocks.createShare,
    toUiMessages: () => mocks.messages,
  };
});

import ChatView from "@/views/ChatView";

const sessionId = "11111111-1111-4111-8111-111111111111";
const session = {
  id: sessionId,
  title: "Private title",
  selected_model: "google/gemma-4-31B-it",
  created_at: "2026-07-28T20:00:00Z",
  updated_at: "2026-07-28T20:00:00Z",
  message_count: 1,
  is_busy: false,
};

let queryClient: QueryClient;

const LocationProbe = () => {
  const location = useLocation();
  return <output data-testid="chat-location">{location.pathname}</output>;
};

function chatElement(path = `/chat/${sessionId}`) {
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/chat/:sessionId?"
            element={<><ChatView /><LocationProbe /></>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function renderChat(path = `/chat/${sessionId}`) {
  return render(chatElement(path));
}

beforeEach(() => {
  vi.restoreAllMocks();
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  localStorage.clear();
  sessionStorage.clear();
  vi.unstubAllEnvs();
  mocks.busy = false;
  mocks.messages.splice(0, mocks.messages.length, {
    id: "user-1",
    role: "user",
    text: "Question",
    revision: 1,
    status: "complete",
  });
  mocks.chatOptions = null;
  mocks.send.mockReset().mockReturnValue(true);
  mocks.hfLoginUrl.mockReset().mockImplementation(() => window.location.href);
  mocks.load.mockReset();
  mocks.getSession.mockReset().mockResolvedValue({
    ...session,
    transcript_status: "ready",
    messages: [],
  });
  mocks.listSessions.mockReset().mockResolvedValue([session]);
  mocks.getChatModels.mockReset().mockResolvedValue({
    items: [{ id: session.selected_model, label: "Default" }],
    default_model: session.selected_model,
  });
  mocks.createShare.mockReset().mockResolvedValue({
    share_id: "22222222-2222-4222-8222-222222222222",
    public_path: "/share/22222222-2222-4222-8222-222222222222",
    created_at: "2026-07-28T20:00:00Z",
    updated_at: "2026-07-28T20:00:00Z",
  });
  mocks.toast.mockReset();
  mocks.clipboardWrite.mockReset().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: mocks.clipboardWrite },
  });
});

describe("ChatView inference authorization", () => {
  it("loads a reserved chat before auto-sending its queued home-page prompt", async () => {
    mocks.messages.length = 0;
    let resolveSession!: (value: typeof session & { transcript_status: string; messages: never[] }) => void;
    let resolveBilling!: (value: Response) => void;
    mocks.getSession.mockReturnValueOnce(new Promise((resolve) => {
      resolveSession = resolve;
    }));
    sessionStorage.setItem("pwc:chat-oauth-draft", "Compare recent vision-language models");
    sessionStorage.setItem("pwc:chat-oauth-model", session.selected_model);
    sessionStorage.setItem("pwc:chat-oauth-auto-send", "1");
    vi.spyOn(globalThis, "fetch").mockReturnValueOnce(new Promise((resolve) => {
      resolveBilling = resolve;
    }));

    renderChat();

    await waitFor(() => expect(mocks.getSession).toHaveBeenCalledWith(sessionId));
    expect(await screen.findByText("Compare recent vision-language models")).toBeVisible();
    expect(screen.queryByText("Ask Papers With Code")).not.toBeInTheDocument();
    expect(mocks.send).not.toHaveBeenCalled();

    resolveSession({ ...session, transcript_status: "ready", messages: [] });

    await waitFor(() => expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/me/inference-billing"),
      expect.anything(),
    ));

    resolveBilling(new Response(JSON.stringify({ connected: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));

    await waitFor(() => expect(mocks.send).toHaveBeenCalledWith(
      "Compare recent vision-language models",
    ));
  });

  it("starts inference authorization on the first chat when permission is missing", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ connected: false }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const user = userEvent.setup();
    renderChat("/chat");

    const composer = await screen.findByRole("textbox");
    await user.type(composer, "What is new in vision-language models?");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() => expect(mocks.hfLoginUrl).toHaveBeenCalledWith("/chat", true));
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/me/inference-billing"),
      expect.objectContaining({ credentials: "include" }),
    );
    expect(sessionStorage.getItem("pwc:chat-oauth-draft")).toBe(
      "What is new in vision-language models?",
    );
    expect(sessionStorage.getItem("pwc:chat-oauth-auto-send")).toBe("1");
    expect(mocks.send).not.toHaveBeenCalled();
  });

  it("sends directly when inference permission is already connected", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ connected: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const user = userEvent.setup();
    renderChat("/chat");

    const composer = await screen.findByRole("textbox");
    await user.type(composer, "Explain this benchmark");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() => expect(mocks.send).toHaveBeenCalledWith("Explain this benchmark"));
    expect(mocks.hfLoginUrl).not.toHaveBeenCalled();
  });
});

describe("ChatView billing notice", () => {
  it("can be dismissed permanently in this browser", async () => {
    vi.stubEnv("VITE_CHAT_LIVE", "1");
    const user = userEvent.setup();
    const rendered = renderChat();

    const dismiss = await screen.findByRole("button", {
      name: "Dismiss billing notice",
    });
    expect(screen.getByRole("link", { name: "Review usage" })).toBeVisible();

    await user.click(dismiss);

    expect(screen.queryByRole("link", { name: "Review usage" })).not.toBeInTheDocument();
    expect(localStorage.getItem("pwc.chat.billing-notice-dismissed.v1")).toBe("1");

    rendered.unmount();
    renderChat();
    await waitFor(() => expect(mocks.listSessions).toHaveBeenCalled());
    expect(screen.queryByRole("link", { name: "Review usage" })).not.toBeInTheDocument();
  });
});

describe("ChatView sharing", () => {
  it("is absent before a persisted non-empty session exists", async () => {
    renderChat("/chat");
    await waitFor(() => expect(mocks.listSessions).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "Share conversation" })).not.toBeInTheDocument();
  });

  it("publishes, copies a current-origin URL, and shows the exact success toast", async () => {
    const user = userEvent.setup();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: mocks.clipboardWrite },
    });
    renderChat();
    const button = await screen.findByRole("button", { name: "Share conversation" });

    await user.click(button);

    expect(mocks.createShare).toHaveBeenCalledWith(sessionId);
    expect(mocks.clipboardWrite).toHaveBeenCalledWith(
      `${window.location.origin}/share/22222222-2222-4222-8222-222222222222`,
    );
    expect(mocks.toast).toHaveBeenCalledWith(expect.objectContaining({
      title: "Public link copied to your clipboard",
      description: "Anyone with this link can see this conversation.",
    }));
    expect(button).toHaveTextContent("Share");
  });

  it("keeps the share and opens one manual-copy fallback on clipboard rejection", async () => {
    const user = userEvent.setup();
    mocks.clipboardWrite.mockRejectedValueOnce(new Error("denied"));
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: mocks.clipboardWrite },
    });
    renderChat();

    await user.click(await screen.findByRole("button", { name: "Share conversation" }));

    expect(await screen.findByRole("dialog", { name: "Public link created" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Public conversation link" })).toHaveValue(
      `${window.location.origin}/share/22222222-2222-4222-8222-222222222222`,
    );
    expect(mocks.createShare).toHaveBeenCalledTimes(1);
    expect(mocks.toast).not.toHaveBeenCalledWith(expect.objectContaining({
      title: "Public link copied to your clipboard",
    }));
  });

  it("disables sharing while generation is active", async () => {
    const rendered = renderChat();
    expect(await screen.findByRole("button", { name: "Share conversation" })).toBeEnabled();
    mocks.busy = true;
    rendered.rerender(chatElement());
    expect(screen.getByRole("button", { name: "Share conversation" })).toBeDisabled();
  });

  it("disables sharing while its publication request is pending", async () => {
    const user = userEvent.setup();
    let resolveShare!: (value: {
      share_id: string;
      public_path: string;
      created_at: string;
      updated_at: string;
    }) => void;
    mocks.createShare.mockReturnValueOnce(new Promise((resolve) => {
      resolveShare = resolve;
    }));
    renderChat();

    const button = await screen.findByRole("button", { name: "Share conversation" });
    await user.click(button);

    expect(button).toBeDisabled();
    resolveShare({
      share_id: "22222222-2222-4222-8222-222222222222",
      public_path: "/share/22222222-2222-4222-8222-222222222222",
      created_at: "2026-07-28T20:00:00Z",
      updated_at: "2026-07-28T20:00:00Z",
    });
    await waitFor(() => expect(button).toBeEnabled());
  });

  it("does not claim copy success when publication fails", async () => {
    const user = userEvent.setup();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: mocks.clipboardWrite },
    });
    mocks.createShare.mockRejectedValueOnce(new Error("Not allowed"));
    renderChat();
    await user.click(await screen.findByRole("button", { name: "Share conversation" }));

    expect(mocks.clipboardWrite).not.toHaveBeenCalled();
    expect(mocks.toast).toHaveBeenCalledWith(expect.objectContaining({
      variant: "destructive",
      title: "Share failed",
    }));
    expect(mocks.toast).not.toHaveBeenCalledWith(expect.objectContaining({
      title: "Public link copied to your clipboard",
    }));
  });
});

describe("ChatView focus refresh", () => {
  it("refreshes the sidebar without reloading and aborting the active transcript", async () => {
    renderChat();
    await waitFor(() => expect(mocks.load).toHaveBeenCalledTimes(1));
    mocks.getSession.mockClear();
    mocks.load.mockClear();
    mocks.listSessions.mockClear();

    window.dispatchEvent(new Event("focus"));

    await waitFor(() => expect(mocks.listSessions).toHaveBeenCalledTimes(1));
    expect(mocks.getSession).not.toHaveBeenCalled();
    expect(mocks.load).not.toHaveBeenCalled();
  });
});

describe("ChatView navigation", () => {
  it("loads an earlier conversation while another response is generating", async () => {
    const earlierSession = {
      ...session,
      id: "33333333-3333-4333-8333-333333333333",
      title: "Earlier chat",
      updated_at: "2026-07-27T20:00:00Z",
    };
    mocks.busy = true;
    mocks.listSessions.mockResolvedValue([session, earlierSession]);
    mocks.getSession.mockImplementation(async (id: string) => ({
      ...(id === earlierSession.id ? earlierSession : session),
      transcript_status: "ready",
      messages: [],
    }));
    const user = userEvent.setup();
    renderChat();
    await waitFor(() => expect(mocks.load).toHaveBeenCalledTimes(1));
    mocks.load.mockClear();

    await user.click(await screen.findByText("Earlier chat", { selector: ".chat-session-title" }));

    await waitFor(() => expect(mocks.getSession).toHaveBeenCalledWith(earlierSession.id));
    await waitFor(() => expect(mocks.load).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("Loading conversation…")).not.toBeInTheDocument();
  });
});

describe("ChatView new-session sidebar", () => {
  it("replaces the new-chat URL with the admitted session ID", async () => {
    mocks.listSessions.mockResolvedValue([]);
    renderChat("/chat");
    await waitFor(() => expect(mocks.listSessions).toHaveBeenCalled());

    act(() => mocks.chatOptions?.onSessionId(sessionId));

    expect(await screen.findByTestId("chat-location")).toHaveTextContent(
      `/chat/${sessionId}`,
    );
  });

  it("inserts the session at stream start and applies streamed title deltas", async () => {
    mocks.listSessions.mockResolvedValue([]);
    renderChat("/chat");
    await waitFor(() => expect(mocks.listSessions).toHaveBeenCalled());

    act(() => mocks.chatOptions?.onSessionId(sessionId));
    expect(await screen.findByText("New chat", { selector: ".chat-session-title" })).toBeInTheDocument();

    act(() => mocks.chatOptions?.onTitle("Good OCR Models"));
    expect(screen.getByText("Good OCR Models", { selector: ".chat-session-title" })).toBeInTheDocument();
  });
});
