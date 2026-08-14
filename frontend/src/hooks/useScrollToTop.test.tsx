import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useScrollToTop } from "@/hooks/useScrollToTop";

const ScrollHarness = () => {
  const navigate = useNavigate();
  useScrollToTop();

  return (
    <>
      <button onClick={() => navigate("?has_code=true")}>
        Change filter
      </button>
      <button onClick={() => navigate("/tasks/image-classification")}>
        Change page
      </button>
    </>
  );
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useScrollToTop", () => {
  it("preserves scroll for query changes and resets it for pathname changes", async () => {
    const scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => {});
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={["/tasks/ocr"]}>
        <ScrollHarness />
      </MemoryRouter>,
    );

    expect(scrollTo).toHaveBeenCalledWith(0, 0);
    scrollTo.mockClear();

    await user.click(screen.getByRole("button", { name: "Change filter" }));
    expect(scrollTo).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Change page" }));
    expect(scrollTo).toHaveBeenCalledWith(0, 0);
  });
});
