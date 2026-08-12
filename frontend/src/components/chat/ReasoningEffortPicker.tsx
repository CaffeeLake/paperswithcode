import React, { useEffect, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";

import type { ReasoningEffort } from "@/lib/chat";

const OPTIONS: Array<{
  value: ReasoningEffort;
  label: string;
  description: string;
}> = [
  { value: "low", label: "Low", description: "Faster and more concise" },
  { value: "high", label: "High", description: "More thorough" },
  { value: "max", label: "Max", description: "Deepest and slowest" },
];

interface ReasoningEffortPickerProps {
  value: ReasoningEffort;
  onChange: (value: ReasoningEffort) => void;
  disabled?: boolean;
}

const ReasoningEffortPicker: React.FC<ReasoningEffortPickerProps> = ({
  value,
  onChange,
  disabled = false,
}) => {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const selected = OPTIONS.find((option) => option.value === value) ?? OPTIONS[0];

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  useEffect(() => {
    if (disabled) setOpen(false);
  }, [disabled]);

  return (
    <div className="chat-effort-picker" ref={rootRef}>
      <button
        type="button"
        className="chat-effort-trigger"
        aria-label={`Reasoning effort: ${selected.label}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
      >
        <span>Effort: {selected.label}</span>
        <ChevronDown size={13} aria-hidden="true" />
      </button>
      {open && (
        <div className="chat-effort-menu" role="listbox" aria-label="Reasoning effort">
          <div className="chat-effort-menu-label" aria-hidden="true">
            Reasoning effort
          </div>
          {OPTIONS.map((option) => (
            <button
              type="button"
              key={option.value}
              className={`chat-effort-option${option.value === value ? " is-selected" : ""}`}
              role="option"
              aria-selected={option.value === value}
              onClick={() => {
                onChange(option.value);
                setOpen(false);
              }}
            >
              <span className="chat-effort-option-copy">
                <strong>{option.label}</strong>
                <small>{option.description}</small>
              </span>
              {option.value === value && <Check size={15} aria-hidden="true" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default ReasoningEffortPicker;
