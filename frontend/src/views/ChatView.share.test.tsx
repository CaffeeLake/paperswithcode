import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
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
  selected_model: "deepseek-ai/DeepSeek-V4-Flash",
  created_at: "2026-07-28T20:00:00Z",
  updated_at: "2026-07-28T20:00:00Z",
  message_count: 1,
  is_busy: false,
};

function chatElement(path = `/chat/${sessionId}`) {
  return (
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/chat/:sessionId?" element={<ChatView />} />
      </Routes>
    </MemoryRouter>
  );
}

function renderChat(path = `/chat/${sessionId}`) {
  return render(chatElement(path));
}

beforeEach(() => {
  mocks.busy = false;
  mocks.chatOptions = null;
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

describe("ChatView new-session sidebar", () => {
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
