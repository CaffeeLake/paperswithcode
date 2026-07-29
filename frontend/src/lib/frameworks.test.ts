import { describe, expect, it } from "vitest";

import { PLATFORM_LABELS } from "./frameworks";

describe("framework catalogue types", () => {
  it("defines every supported platform label", () => {
    expect(PLATFORM_LABELS).toEqual({
      gpu: "GPU",
      cpu: "CPU",
      apple: "Apple silicon",
    });
  });
});
