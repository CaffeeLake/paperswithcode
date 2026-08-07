/** Native textarea chat composer with structured inline paper mentions. */

import React, { useEffect, useRef, useState } from "react";

import { PaperMentionPicker } from "@/components/chat/PaperMentionPicker";
import { ArrowUpIcon, Spinner } from "@/components/chat/icons";
import ModelPicker, { type ModelPickerOption } from "@/components/chat/ModelPicker";
import { usePaperMentions } from "@/components/chat/usePaperMentions";
import WebSearchToggle from "@/components/chat/WebSearchToggle";
import type { ChatDraft } from "@/lib/chat";

interface ComposerProps {
  onSend: (draft: ChatDraft) => void;
  busy?: boolean;
  placeholder?: string;
  autoFocus?: boolean;
  draft?: ChatDraft;
  onDraftChange?: (value: ChatDraft) => void;
  onStop?: () => void;
  models?: ModelPickerOption[];
  selectedModel?: string;
  onModelChange?: (model: string) => void;
  disabled?: boolean;
  describedBy?: string;
  paperMentionsEnabled?: boolean;
  webSearchAvailable?: boolean;
  webSearchEnabled?: boolean;
  onWebSearchChange?: (enabled: boolean) => void;
}

const EMPTY_DRAFT: ChatDraft = { text: "", paperMentions: [] };

const Composer: React.FC<ComposerProps> = ({
  onSend, busy, placeholder, autoFocus, draft, onDraftChange, onStop,
  models = [], selectedModel, onModelChange, disabled = false, describedBy,
  paperMentionsEnabled = false,
  webSearchAvailable = false,
  webSearchEnabled = false,
  onWebSearchChange,
}) => {
  const [localDraft, setLocalDraft] = useState<ChatDraft>(EMPTY_DRAFT);
  const value = draft ?? localDraft;
  const ref = useRef<HTMLTextAreaElement>(null);
  const change = (next: ChatDraft) => {
    if (!draft) setLocalDraft(next);
    onDraftChange?.(next);
  };
  const mentions = usePaperMentions({
    draft: value,
    onChange: change,
    enabled: paperMentionsEnabled,
    textareaRef: ref,
  });

  useEffect(() => {
    const el = ref.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
    }
  }, [value.text]);

  useEffect(() => { if (autoFocus) ref.current?.focus(); }, [autoFocus]);

  const submit = () => {
    const leading = value.text.length - value.text.trimStart().length;
    const text = value.text.trim();
    if (!text || busy || disabled) return;
    const end = leading + text.length;
    const normalized: ChatDraft = {
      text,
      paperMentions: value.paperMentions
        .filter((mention) => mention.start >= leading && mention.end <= end)
        .map((mention) => ({ ...mention, start: mention.start - leading, end: mention.end - leading })),
    };
    onSend(normalized);
  };

  return (
    <div className="chat-composer">
      {value.paperMentions.length > 0 && <div className="chat-paper-chips" aria-label="Attached papers">
        {value.paperMentions.map((mention) => <span className={`chat-paper-chip${mention.unavailable ? " is-unavailable" : ""}`} key={mention.key}>
          <span aria-hidden="true">▤</span>{mention.title}
          <button type="button" onClick={() => mentions.remove(mention.key)} aria-label={`Remove ${mention.title}`}>×</button>
        </span>)}
      </div>}
      <div className="chat-composer-textarea-wrap">
        <textarea
          ref={ref}
          rows={1}
          value={value.text}
          placeholder={placeholder || "Ask anything about research…"}
          onChange={(event) => mentions.updateText(event.target.value, event.target.selectionStart)}
          onSelect={(event) => mentions.refresh(event.currentTarget.selectionStart)}
          onClick={(event) => mentions.refresh(event.currentTarget.selectionStart)}
          onBlur={(event) => {
            if (!event.relatedTarget?.closest?.(".chat-paper-picker")) window.setTimeout(mentions.close, 0);
          }}
          onKeyDown={(event) => {
            if (mentions.keyDown(event)) return;
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              submit();
            }
          }}
          role="combobox"
          aria-expanded={mentions.open}
          aria-controls={mentions.open ? mentions.pickerId : undefined}
          aria-activedescendant={mentions.open && mentions.results.length ? `${mentions.optionIdPrefix}-${mentions.activeIndex}` : undefined}
          aria-autocomplete="list"
          aria-describedby={[describedBy, mentions.message ? "chat-paper-mention-message" : null].filter(Boolean).join(" ") || undefined}
        />
        <PaperMentionPicker
          open={mentions.open}
          query={mentions.query}
          results={mentions.results}
          activeIndex={mentions.activeIndex}
          loading={mentions.loading}
          error={mentions.error}
          onSelect={mentions.select}
          id={mentions.pickerId}
          optionIdPrefix={mentions.optionIdPrefix}
        />
      </div>
      {mentions.message && <div id="chat-paper-mention-message" className="chat-paper-mention-message" role="alert">{mentions.message}</div>}
      <div className="chat-composer-row">
        <div className="chat-composer-tools">
          {models.length > 0 && selectedModel && onModelChange && <ModelPicker models={models} selectedModel={selectedModel} onModelChange={onModelChange} disabled={busy} />}
          {webSearchAvailable && onWebSearchChange && (
            <WebSearchToggle
              enabled={webSearchEnabled}
              onChange={onWebSearchChange}
              disabled={busy}
            />
          )}
          <span className="chat-composer-hint">Enter to send · Shift+Enter for newline</span>
        </div>
        <button type="button" className={`chat-send${(busy || value.text.trim()) ? " chat-send-on" : ""}`} onClick={busy ? onStop : submit} disabled={disabled || (busy ? !onStop : !value.text.trim())} aria-label={busy ? "Stop generating" : "Send message"}>
          {busy ? (onStop ? <span aria-hidden="true">■</span> : <Spinner light />) : <ArrowUpIcon />}
        </button>
      </div>
    </div>
  );
};

export default Composer;
