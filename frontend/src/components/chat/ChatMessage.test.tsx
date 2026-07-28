import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

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
});

describe("AssistantMessage", () => {
  const renderAssistant = (msg: ChatMessageType) => render(
    <AssistantMessage msg={msg} papers={{}} onToggleBlock={() => undefined} />,
  );

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
