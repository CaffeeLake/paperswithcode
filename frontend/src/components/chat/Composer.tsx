/**
 * Chat composer: autosizing textarea, Enter-to-send (Shift+Enter for a
 * newline), and the research-model picker.
 */

import React, { useEffect, useRef, useState } from "react";

import { ArrowUpIcon, Spinner } from "@/components/chat/icons";
import ModelPicker, { type ModelPickerOption } from "@/components/chat/ModelPicker";

interface ComposerProps {
  onSend: (text: string) => void;
  busy?: boolean;
  placeholder?: string;
  autoFocus?: boolean;
  draft?: string;
  onDraftChange?: (value: string) => void;
  onStop?: () => void;
  models?: ModelPickerOption[];
  selectedModel?: string;
  onModelChange?: (model: string) => void;
  disabled?: boolean;
  describedBy?: string;
}

const Composer: React.FC<ComposerProps> = ({ onSend, busy, placeholder, autoFocus, draft, onDraftChange, onStop, models = [], selectedModel, onModelChange, disabled = false, describedBy }) => {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
    }
  }, [value]);

  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus]);

  useEffect(() => {
    if (draft !== undefined) setValue(draft);
  }, [draft]);

  const submit = () => {
    const text = value.trim();
    if (!text || busy || disabled) return;
    setValue("");
    onDraftChange?.("");
    onSend(text);
  };

  return (
    <div className="chat-composer">
      <textarea
        ref={ref}
        rows={1}
        value={value}
        placeholder={placeholder || "Ask anything about research…"}
        onChange={(e) => { setValue(e.target.value); onDraftChange?.(e.target.value); }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        aria-describedby={describedBy}
      />
      <div className="chat-composer-row">
        <div className="chat-composer-tools">
          {models.length > 0 && selectedModel && onModelChange && (
            <ModelPicker
              models={models}
              selectedModel={selectedModel}
              onModelChange={onModelChange}
              disabled={busy}
            />
          )}
          <span className="chat-composer-hint">Enter to send · Shift+Enter for newline</span>
        </div>
        <button
          type="button"
          className={`chat-send${(busy || value.trim()) ? " chat-send-on" : ""}`}
          onClick={busy ? onStop : submit}
          disabled={disabled || (busy ? !onStop : !value.trim())}
          aria-label={busy ? "Stop generating" : "Send message"}
        >
          {busy ? (onStop ? <span aria-hidden="true">■</span> : <Spinner light />) : <ArrowUpIcon />}
        </button>
      </div>
    </div>
  );
};

export default Composer;
