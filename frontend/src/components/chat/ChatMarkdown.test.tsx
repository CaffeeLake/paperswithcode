import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChatMarkdown } from "@/components/chat/ChatMarkdown";
import { normalizeChatMath } from "@/components/chat/chatMarkdownMath";

describe("ChatMarkdown math", () => {
  it("renders LaTeX display delimiters emitted by chat models", () => {
    const { container } = render(
      <ChatMarkdown
        text={String.raw`The core operation is:

\[
\operatorname{Attention}(Q,K,V)
=\operatorname{softmax}\left(\frac{QK^\top}{\sqrt{d_k}}\right)V
\]`}
        papers={{}}
      />,
    );

    expect(container.querySelector(".katex-display")).not.toBeNull();
    expect(container.textContent).toContain("Attention");
  });

  it("renders LaTeX inline delimiters", () => {
    const { container } = render(
      <ChatMarkdown text={String.raw`Use \(QK^\top\) here.`} papers={{}} />,
    );

    expect(container.querySelector(".katex")).not.toBeNull();
    expect(container.querySelector(".katex-display")).toBeNull();
  });

  it("leaves delimiters in code and incomplete math unchanged", () => {
    const markdown = [
      "Inline: `\\(literal\\)`",
      "",
      "```tex",
      String.raw`\[literal\]`,
      "```",
      "",
      String.raw`Incomplete: \[x`,
    ].join("\n");

    expect(normalizeChatMath(markdown)).toBe(markdown);
  });
});
