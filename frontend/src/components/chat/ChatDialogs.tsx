import { useEffect, useRef, useState } from "react";

export function ChatCapacityDialog({
  retryAt,
  onRetry,
  onCancel,
}: {
  retryAt: number;
  onRetry: () => void;
  onCancel: () => void;
}) {
  const [remaining, setRemaining] = useState(
    () => Math.max(0, Math.ceil((retryAt - Date.now()) / 1_000)),
  );
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previouslyFocused = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    cancelRef.current?.focus();
    const update = () => setRemaining(
      Math.max(0, Math.ceil((retryAt - Date.now()) / 1_000)),
    );
    update();
    const timer = window.setInterval(update, 250);
    return () => {
      window.clearInterval(timer);
      previouslyFocused?.focus();
    };
  }, [retryAt]);

  return (
    <div className="chat-capacity-dialog-backdrop" role="presentation">
      <div
        className="chat-capacity-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="chat-capacity-dialog-title"
        aria-describedby="chat-capacity-dialog-description"
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            onCancel();
          }
        }}
      >
        <h2 id="chat-capacity-dialog-title">All research slots are currently in use</h2>
        <p id="chat-capacity-dialog-description">
          Your message was not sent or billed. Try again in a few seconds.
        </p>
        <p className="chat-capacity-countdown" aria-live="polite">
          {remaining > 0
            ? `Try again available in ${remaining} second${remaining === 1 ? "" : "s"}.`
            : "You can try again now."}
        </p>
        <div className="chat-capacity-dialog-actions">
          <button type="button" className="chat-capacity-cancel" ref={cancelRef} onClick={onCancel}>Cancel</button>
          <button type="button" className="chat-capacity-retry" disabled={remaining > 0} onClick={onRetry}>Try again</button>
        </div>
      </div>
    </div>
  );
}

export function ChatDisabledDialog({ onClose }: { onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previouslyFocused = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    closeRef.current?.focus();
    return () => previouslyFocused?.focus();
  }, []);
  return <div className="chat-capacity-dialog-backdrop" role="presentation">
    <div className="chat-capacity-dialog" role="dialog" aria-modal="true"
      aria-labelledby="chat-disabled-title" aria-describedby="chat-disabled-description"
      onKeyDown={(event) => { if (event.key === "Escape") { event.preventDefault(); onClose(); } }}>
      <h2 id="chat-disabled-title">Chat is temporarily disabled</h2>
      <p id="chat-disabled-description">We've temporarily paused new research runs. Your message wasn't sent, and your draft is still here. Please try again later.</p>
      <div className="chat-capacity-dialog-actions">
        <button ref={closeRef} type="button" className="chat-capacity-cancel" onClick={onClose}>Keep editing</button>
      </div>
    </div>
  </div>;
}

export function ChatShareDialog({
  url,
  onClose,
}: {
  url: string;
  onClose: () => void;
}) {
  if (!url) return null;
  return (
    <div className="chat-share-dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <div
        className="chat-share-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="chat-share-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <h2 id="chat-share-dialog-title">Public link created</h2>
        <p>
          Anyone with this link can see this conversation. It could not be
          copied automatically, so copy it manually:
        </p>
        <input
          readOnly
          value={url}
          aria-label="Public conversation link"
          autoFocus
          onFocus={(event) => event.currentTarget.select()}
        />
        <button type="button" onClick={onClose}>Close</button>
      </div>
    </div>
  );
}
