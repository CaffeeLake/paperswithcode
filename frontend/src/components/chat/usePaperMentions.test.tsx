import { describe, expect, it } from "vitest";

import { activePaperMention, reconcilePaperMentions } from "./usePaperMentions";
import type { PaperMentionDraft } from "@/lib/chat";

const mention: PaperMentionDraft = {
  key: "one", route_id: "2501.00001", title: "Paper", source: "arxiv", start: 6, end: 12,
};

describe("paper mention draft mechanics", () => {
  it("opens on eligible at-signs but not email-like text", () => {
    expect(activePaperMention("ask @deep seek", 14)).toEqual({ start: 4, end: 14, query: "deep seek" });
    expect(activePaperMention("me@example", 10)).toBeNull();
    expect(activePaperMention("@", 1)).toEqual({ start: 0, end: 1, query: "" });
  });

  it("shifts mentions before them and detaches mentions edited through", () => {
    expect(reconcilePaperMentions("Read: @Paper", "Please Read: @Paper", [mention]))
      .toEqual([{ ...mention, start: 13, end: 19 }]);
    expect(reconcilePaperMentions("Read: @Paper", "Read: @Piper", [mention])).toEqual([]);
  });
});
