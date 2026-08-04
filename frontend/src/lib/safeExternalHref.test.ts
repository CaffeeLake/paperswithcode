import { describe, expect, it } from "vitest";

import { safeExternalHref } from "./safeExternalHref";

describe("safeExternalHref", () => {
  it("accepts absolute HTTP(S) links", () => {
    expect(safeExternalHref("https://example.com/project")).toBe(
      "https://example.com/project",
    );
    expect(safeExternalHref("http://example.com/")).toBe("http://example.com/");
  });

  it.each([
    "javascript:alert(1)",
    "data:text/html,bad",
    "file:///etc/passwd",
    "//example.com/path",
    "https://user:pass@example.com/",
    "https://example.com/ bad",
    "not a url",
  ])("rejects unsafe link %s", (value) => {
    expect(safeExternalHref(value)).toBeNull();
  });
});
