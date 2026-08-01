import { describe, expect, it } from "vitest";

import { hfLoginUrl } from "@/components/HfSignInButton";

describe("hfLoginUrl", () => {
  it("keeps ordinary sign-in limited to account identity", () => {
    const url = new URL(hfLoginUrl("/settings"), window.location.origin);

    expect(url.pathname).toBe("/api/v1/auth/hf/login");
    expect(url.searchParams.get("return_to")).toBe("/settings");
    expect(url.searchParams.has("authorize_inference")).toBe(false);
  });

  it("marks chat authorization as an inference permission request", () => {
    const url = new URL(hfLoginUrl("/chat", true), window.location.origin);

    expect(url.searchParams.get("return_to")).toBe("/chat");
    expect(url.searchParams.get("authorize_inference")).toBe("true");
  });
});
