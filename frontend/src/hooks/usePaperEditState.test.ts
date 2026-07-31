import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  parseFreshAuthEditSection,
  usePaperEditState,
} from "./usePaperEditState";

describe("usePaperEditState", () => {
  it("keeps at most one editor active", () => {
    const { result } = renderHook(() => usePaperEditState());

    act(() => result.current.openEditor("tasks"));
    expect(result.current.activeEditor).toBe("tasks");

    act(() => result.current.openEditor("methods"));
    expect(result.current.activeEditor).toBe("methods");

    act(() => result.current.setEditorOpen("methods", false));
    expect(result.current.activeEditor).toBeNull();
  });

  it("does not let a stale close event dismiss the active editor", () => {
    const { result } = renderHook(() => usePaperEditState());

    act(() => result.current.openEditor("methods"));
    act(() => result.current.setEditorOpen("tasks", false));

    expect(result.current.activeEditor).toBe("methods");
  });
});

describe("parseFreshAuthEditSection", () => {
  it.each([
    ["tasks", "tasks"],
    ["methods", "methods"],
    ["evaluations", "results"],
    ["repositories", "repositories"],
    ["project_pages", "project-pages"],
    ["hf_artifacts", "hf-artifacts"],
    ["organizations", "organizations"],
    ["source_url", "source-url"],
  ] as const)("maps %s to %s", (storedSection, editor) => {
    expect(parseFreshAuthEditSection(storedSection)).toBe(editor);
  });

  it("ignores unknown stored sections", () => {
    expect(parseFreshAuthEditSection("unknown")).toBeNull();
  });
});
