import { afterEach, describe, expect, it, vi } from "vitest";

import { adminDashboardUrl } from "./apiUrl";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("adminDashboardUrl", () => {
  it("uses the current origin when there is no separate auth authority", () => {
    vi.stubEnv("VITE_AUTH_URL", "");

    expect(adminDashboardUrl()).toBe("/admin-dashboard");
  });

  it("uses the production auth authority in a staging build", () => {
    vi.stubEnv("VITE_AUTH_URL", "https://paperswithcode.co/");

    expect(adminDashboardUrl()).toBe(
      "https://paperswithcode.co/admin-dashboard",
    );
  });
});
