import { describe, expect, it } from "vitest";

import { shouldReloadChunk } from "@/lib/chunkReload";

describe("shouldReloadChunk", () => {
  it("allows the first recovery reload", () => {
    expect(shouldReloadChunk(null, 100_000)).toBe(true);
  });

  it("prevents a reload loop during the cooldown", () => {
    expect(shouldReloadChunk("90000", 100_000)).toBe(false);
  });

  it("allows recovery again after the cooldown", () => {
    expect(shouldReloadChunk("10000", 100_000)).toBe(true);
  });

  it("recovers from invalid stored state", () => {
    expect(shouldReloadChunk("not-a-timestamp", 100_000)).toBe(true);
  });
});
