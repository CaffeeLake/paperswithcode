import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const readerStyles = readFileSync(
  resolve(process.cwd(), "src/styles/features/paper-reader.css"),
  "utf8",
);

describe("paper reader styles", () => {
  it("keeps the PDF text overlay invisible while text is selected", () => {
    expect(readerStyles).toMatch(/\.pdf-page \.textLayer ::selection \{[^}]*color: transparent;/);
    expect(readerStyles).toMatch(/\.pdf-page \.textLayer ::-moz-selection \{[^}]*color: transparent;/);
  });
});
