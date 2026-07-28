import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { UserMessage } from "@/components/chat/ChatMessage";

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
