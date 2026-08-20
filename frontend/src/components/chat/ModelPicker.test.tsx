import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ModelPicker from "@/components/chat/ModelPicker";

const models = [
  { id: "hf-a", label: "HF Model A", provider: "huggingface" as const },
  { id: "hf-b", label: "HF Model B", provider: "huggingface" as const },
  { id: "oa-a", label: "OpenAI Model A", provider: "openai" as const },
  { id: "or-a", label: "OpenRouter Model A", provider: "openrouter" as const },
];

describe("ModelPicker", () => {
  it("renders one production model as a read-only label", () => {
    render(
      <ModelPicker
        models={[models[0]]}
        selectedModel="hf-a"
        onModelChange={() => undefined}
      />,
    );

    expect(screen.getByLabelText("Research model")).toHaveTextContent("HF Model A");
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("groups models by inference provider", () => {
    render(
      <ModelPicker
        models={models}
        selectedModel="hf-a"
        onModelChange={() => undefined}
      />,
    );

    const groups = screen.getByRole("combobox").querySelectorAll("optgroup");
    expect([...groups].map((group) => group.label)).toEqual([
      "Hugging Face Inference Providers",
      "OpenRouter",
      "OpenAI",
    ]);
    expect([...groups[0].querySelectorAll("option")].map((option) => option.value))
      .toEqual(["hf-a", "hf-b"]);
    expect([...groups[1].querySelectorAll("option")].map((option) => option.value))
      .toEqual(["or-a"]);
    expect([...groups[2].querySelectorAll("option")].map((option) => option.value))
      .toEqual(["oa-a"]);
  });

  it("sizes the picker from the selected label", () => {
    render(
      <ModelPicker
        models={models}
        selectedModel="or-a"
        onModelChange={() => undefined}
      />,
    );

    const select = screen.getByRole("combobox");
    const sizer = select.closest(".chat-model-picker")?.querySelector(".chat-model-picker-sizer");

    expect(select).not.toHaveAttribute("style");
    expect(sizer).toHaveTextContent("OpenRouter Model A");
  });

  it("keeps model selection behavior unchanged", async () => {
    const onModelChange = vi.fn();
    const user = userEvent.setup();
    render(
      <ModelPicker
        models={models}
        selectedModel="hf-a"
        onModelChange={onModelChange}
      />,
    );

    await user.selectOptions(screen.getByRole("combobox"), "or-a");

    expect(onModelChange).toHaveBeenCalledWith("or-a");
  });
});
