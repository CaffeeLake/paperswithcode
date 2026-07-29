import { describe, expect, it } from "vitest";

import type { AuthUser } from "./authContext";
import { paperEditSubmitMode } from "./contributorCapabilities";

const contributor = (
  can_directly_edit_catalog: boolean,
): AuthUser => ({
  hf_subject: "contributor-sub",
  username: "abidlabs",
  name: null,
  avatar_url: null,
  is_admin: false,
  role: "contributor",
  can_contribute: true,
  can_directly_edit_catalog,
});

describe("contributor edit capability", () => {
  it("uses direct APIs only when production capability is explicit", () => {
    expect(paperEditSubmitMode(contributor(true))).toBe("direct");
  });

  it("keeps the same contributor in staging-local pending mode", () => {
    expect(paperEditSubmitMode(contributor(false))).toBe("pending");
  });

  it("keeps ordinary signed-in users pending", () => {
    expect(
      paperEditSubmitMode({
        ...contributor(false),
        username: "ordinary",
        role: null,
        can_contribute: false,
      }),
    ).toBe("pending");
  });
});
