import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AssistantMessage, UserMessage } from "@/components/chat/ChatMessage";
import type { ChatMessage as ChatMessageType } from "@/lib/chat";

afterEach(() => {
  delete (document as Partial<Document>).caretPositionFromPoint;
  delete (document as Partial<Document>).caretRangeFromPoint;
  document.getSelection()?.removeAllRanges();
});

describe("UserMessage", () => {
  it("cancels Safari's second mousedown and selects only the clicked word", () => {
    render(<UserMessage text="What's the SOTA for image classification?" />);
    const message = screen.getByText("What's the SOTA for image classification?");
    const textNode = message.firstChild;
    expect(textNode).toBeInstanceOf(Text);
    Object.defineProperty(document, "caretPositionFromPoint", {
      configurable: true,
      value: () => ({ offsetNode: textNode, offset: 12 }),
    });

    const allowed = fireEvent.mouseDown(message, {
      button: 0,
      clientX: 20,
      clientY: 10,
      detail: 2,
    });

    expect(allowed).toBe(false);
    expect(document.getSelection()?.toString()).toBe("SOTA");
  });

  it("supports Safari's caret range fallback", () => {
    render(<UserMessage text="What's the SOTA for image classification?" />);
    const message = screen.getByText("What's the SOTA for image classification?");
    const textNode = message.firstChild;
    expect(textNode).toBeInstanceOf(Text);
    Object.defineProperty(document, "caretRangeFromPoint", {
      configurable: true,
      value: () => {
        const range = document.createRange();
        range.setStart(textNode!, 22);
        range.collapse(true);
        return range;
      },
    });

    const allowed = fireEvent.mouseDown(message, {
      button: 0,
      clientX: 20,
      clientY: 10,
      detail: 2,
    });

    expect(allowed).toBe(false);
    expect(document.getSelection()?.toString()).toBe("image");
  });

  it("does not interfere with the first press used for drag selection", () => {
    render(<UserMessage text="Select any part of this prompt" />);
    const message = screen.getByText("Select any part of this prompt");

    const allowed = fireEvent.mouseDown(message, { button: 0, detail: 1 });

    expect(allowed).toBe(true);
  });

  it("exposes a keyboard-accessible Codex-style edit action", async () => {
    const user = userEvent.setup();
    let edited = false;
    render(
      <UserMessage
        id="user-1"
        text="Editable prompt"
        editingAllowed
        onEdit={() => { edited = true; }}
      />,
    );

    const edit = screen.getByRole("button", { name: "Edit message" });
    expect(edit).toHaveAttribute("title", "Edit");
    await user.tab();
    expect(edit).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(edited).toBe(true);
  });

  it("focuses the inline editor at the end and resends unchanged text with Enter", async () => {
    const user = userEvent.setup();
    const submissions: string[] = [];
    render(
      <UserMessage
        id="user-1"
        text="Same prompt"
        editing
        editNotice="Sending will replace the response."
        onResend={(text) => { submissions.push(text); return true; }}
      />,
    );

    const editor = screen.getByRole("textbox", { name: "Edit message" });
    expect(editor).toHaveFocus();
    expect(editor).toHaveValue("Same prompt");
    expect((editor as HTMLTextAreaElement).selectionStart).toBe("Same prompt".length);
    expect((editor as HTMLTextAreaElement).selectionEnd).toBe("Same prompt".length);
    expect(screen.getByText("Sending will replace the response.")).toBeVisible();
    expect(screen.getAllByRole("button").map((button) => button.textContent)).toEqual([
      "Cancel",
      "Send",
    ]);

    await user.keyboard("{Enter}");
    expect(submissions).toEqual(["Same prompt"]);
  });

  it("supports Shift+Enter for newlines and Escape to cancel", async () => {
    const user = userEvent.setup();
    let cancelled = false;
    const submissions: string[] = [];
    render(
      <UserMessage
        text="Line one"
        editing
        onCancel={() => { cancelled = true; }}
        onResend={(text) => { submissions.push(text); return true; }}
      />,
    );
    const editor = screen.getByRole("textbox", { name: "Edit message" });

    await user.keyboard("{Shift>}{Enter}{/Shift}Line two");
    expect(editor).toHaveValue("Line one\nLine two");
    expect(submissions).toEqual([]);
    await user.keyboard("{Escape}");
    expect(cancelled).toBe(true);
  });

  it("rejects whitespace-only edits", async () => {
    const user = userEvent.setup();
    render(<UserMessage text="Original" editing onResend={() => true} />);
    const editor = screen.getByRole("textbox", { name: "Edit message" });
    await user.clear(editor);
    await user.type(editor, "   ");
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });
});

describe("AssistantMessage", () => {
  const renderAssistant = (msg: ChatMessageType) => render(
    <AssistantMessage msg={msg} papers={{}} onToggleBlock={() => undefined} />,
  );

  it("renders completed reasoning as Markdown", () => {
    renderAssistant({
      id: "assistant-1",
      role: "assistant",
      blocks: [{
        kind: "reasoning",
        text: "**Researching object detection**\n\n- Check benchmarks\n- Read papers",
        active: false,
        open: true,
      }],
    });

    expect(screen.getByText("Researching object detection").tagName).toBe("STRONG");
    expect(screen.getByRole("list")).toBeVisible();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("links billing failures to the per-user settings page", () => {
    renderAssistant({
      id: "assistant-1",
      role: "assistant",
      error: "Review pay-as-you-go billing.",
      errorCode: "hf_inference_billing_exhausted",
    });

    expect(screen.getByText(/Review pay-as-you-go billing/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Review billing settings" })).toHaveAttribute(
      "href",
      "/settings",
    );
  });

  it("links a missing HF token directly to Settings", () => {
    renderAssistant({
      id: "assistant-1",
      role: "assistant",
      error: "Connect Hugging Face billing in Settings to use this model.",
      errorCode: "hf_inference_billing_required",
    });

    expect(screen.getByRole("link", { name: "Add HF token in Settings" })).toHaveAttribute(
      "href",
      "/settings",
    );
  });

  it("explains the chat limit and offers bulk archiving", async () => {
    const onArchive = vi.fn();
    const user = userEvent.setup();
    render(
      <AssistantMessage
        msg={{
          id: "assistant-1",
          role: "assistant",
          error: "You can have at most 100 chats. Archive chats older than 30 days or delete a chat to create another.",
          errorCode: "chat_session_quota_exceeded",
        }}
        papers={{}}
        onToggleBlock={() => undefined}
        onArchiveOldChats={onArchive}
      />,
    );

    expect(screen.getByText(/at most 100 chats/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Archive chats older than 30 days" }));
    expect(onArchive).toHaveBeenCalledOnce();
  });

  it("shows a thinking status while waiting for the first streamed block", () => {
    renderAssistant({
      id: "assistant-1",
      role: "assistant",
      streaming: true,
      blocks: [],
    });

    expect(screen.getByRole("status")).toHaveTextContent("Thinking…");
    expect(screen.getByText("Thinking…")).toHaveClass("chat-thinking");
  });

  it("renders the delayed workspace status accessibly", () => {
    renderAssistant({
      id: "assistant-1",
      role: "assistant",
      streaming: true,
      status: "Preparing research workspace…",
      blocks: [],
    });

    expect(screen.getByRole("status")).toHaveTextContent(
      "Preparing research workspace…",
    );
  });

  it.each([
    {
      name: "completed reasoning",
      block: { kind: "reasoning", text: "Checked the evidence.", active: false, open: false } as const,
    },
    {
      name: "completed tool call",
      block: {
        kind: "tool",
        id: "tool-1",
        name: "search_papers",
        args: {},
        status: "success",
        open: false,
      } as const,
    },
  ])("shows thinking after a $name while waiting for the next step", ({ block }) => {
    renderAssistant({
      id: "assistant-1",
      role: "assistant",
      streaming: true,
      blocks: [block],
    });

    expect(screen.getByRole("status")).toHaveTextContent("Thinking…");
  });

  it.each([
    {
      name: "active reasoning",
      block: { kind: "reasoning", text: "Still checking.", active: true, open: true } as const,
    },
    {
      name: "running tool call",
      block: {
        kind: "tool",
        id: "tool-1",
        name: "search_papers",
        args: {},
        status: "running",
        open: false,
      } as const,
    },
    {
      name: "streaming answer",
      block: { kind: "answer", text: "The result is", done: false } as const,
    },
  ])("does not add a waiting status during $name", ({ block }) => {
    renderAssistant({
      id: "assistant-1",
      role: "assistant",
      streaming: true,
      blocks: [block],
    });

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("shows a caret only on the active tail answer block", () => {
    const { container } = renderAssistant({
      id: "assistant-1",
      role: "assistant",
      streaming: true,
      blocks: [
        { kind: "answer", text: "First answer segment.", done: false },
        {
          kind: "tool",
          id: "tool-1",
          name: "Bash",
          args: { command: "pwc benchmark list" },
          status: "done",
          hits: 0,
          took_ms: 10,
          results: [],
          open: false,
        },
        { kind: "answer", text: "Latest answer segment.", done: false },
      ],
    });

    expect(container.querySelectorAll(".chat-caret")).toHaveLength(1);
  });

  it("does not show an answer caret while a tool is running", () => {
    const { container } = renderAssistant({
      id: "assistant-1",
      role: "assistant",
      streaming: true,
      blocks: [
        { kind: "answer", text: "I will check the benchmark.", done: false },
        {
          kind: "tool",
          id: "tool-1",
          name: "Bash",
          args: { command: "pwc benchmark list" },
          status: "running",
          open: false,
        },
      ],
    });

    expect(container.querySelectorAll(".chat-caret")).toHaveLength(0);
  });
});
