import { useState } from "react";
import { X as XIcon } from "lucide-react";

import { isChatLive } from "@/lib/chat";
import type { ChatModelChoice } from "@/lib/chatSessions";

const HF_INFERENCE_USAGE_URL = "https://huggingface.co/settings/inference-providers";
const BILLING_NOTICE_DISMISSED_KEY = "pwc.chat.billing-notice-dismissed.v1";

export function BillingNotice({
  provider,
}: {
  provider: ChatModelChoice["provider"];
}) {
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem(BILLING_NOTICE_DISMISSED_KEY) === "1",
  );

  if (!isChatLive() || dismissed || provider !== "huggingface") return null;

  return (
    <div className="chat-billing-notice" role="note">
      <span>
        Hugging Face models use the inference permission granted when you start chatting.
        Included monthly credits are used first, then extra usage requires
        purchased credits. You can choose organization billing in Settings.
      </span>
      <div className="chat-billing-notice-actions">
        <a href="/settings">Review billing</a>
        <a href={HF_INFERENCE_USAGE_URL} target="_blank" rel="noreferrer">Review usage</a>
        <button
          type="button"
          className="chat-billing-notice-dismiss"
          aria-label="Dismiss billing notice"
          title="Dismiss"
          onClick={() => {
            localStorage.setItem(BILLING_NOTICE_DISMISSED_KEY, "1");
            setDismissed(true);
          }}
        >
          <XIcon size={15} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
