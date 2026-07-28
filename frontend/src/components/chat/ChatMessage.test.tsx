import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { UserMessage } from "@/components/chat/ChatMessage";

afterEach(() => {
  delete (document as Partial<Document>).caretPositionFromPoint;
  delete (document as Partial<Document>).caretRangeFromPoint;
  document.getSelection()?.removeAllRanges();
});

describe("UserMessage", () => {
  it("constrains double-click selection to the clicked word", () => {
    render(<UserMessage text="What's the SOTA for image classification?" />);
    const message = screen.getByText("What's the SOTA for image classification?");
    const textNode = message.firstChild;
    expect(textNode).toBeInstanceOf(Text);
    Object.defineProperty(document, "caretPositionFromPoint", {
      configurable: true,
      value: () => ({ offsetNode: textNode, offset: 12 }),
    });

    fireEvent.doubleClick(message, { clientX: 20, clientY: 10 });

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

    fireEvent.doubleClick(message, { clientX: 20, clientY: 10 });

    expect(document.getSelection()?.toString()).toBe("image");
  });
});
