import { useState } from "react";
import { X as XIcon } from "lucide-react";

import { isChatLive } from "@/lib/chat";
import type { ChatModelChoice } from "@/lib/chatSessions";
import { resetTimeLabels, useOpenRouterUsage } from "@/lib/openrouter";

const HF_INFERENCE_USAGE_URL = "https://huggingface.co/settings/inference-providers";
const PRODUCTION_CHAT_URL = "https://paperswithcode.co/chat";
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

export function OpenRouterUsageNotice({
  enabled,
  fallbackEnabled,
  byokExpected,
}: {
  enabled: boolean;
  fallbackEnabled: boolean;
  byokExpected?: boolean;
}) {
  const usageQuery = useOpenRouterUsage(enabled);
  if (!enabled || !usageQuery.data) return null;
  const usage = usageQuery.data;
  const reset = resetTimeLabels(usage.resets_at);
  const stagingFundingDisabled = usage.unavailable_reason === "staging_funding_disabled";
  const sharedUnavailable = usage.unavailable_reason === "shared_credits_exhausted"
    || usage.unavailable_reason === "workspace_limit_exhausted"
    || usage.unavailable_reason === "provider_status_unavailable";
  return <div className="chat-openrouter-usage" role="status">
    <span>
      {stagingFundingDisabled
        ? <strong>Chat is now live on paperswithcode.co</strong>
        : sharedUnavailable
        ? <><strong>Shared OpenRouter credits unavailable</strong> · {usage.remaining_percent}% of your allowance remains</>
        : <><strong>{usage.remaining_percent}% left</strong> this month · resets {reset.local}</>}
    </span>
    {stagingFundingDisabled ? <span>
      <a href={usage.production_chat_url || PRODUCTION_CHAT_URL}>Continue on production</a>
      {fallbackEnabled && " · Your connected OpenRouter key remains available on staging."}
    </span> : (!usage.available || byokExpected) && <span>
      {fallbackEnabled
        ? "Your connected OpenRouter key will be used on your next explicit send."
        : <><a href="/settings#openrouter-byok">Connect your own key in Settings</a> to continue.</>}
    </span>}
  </div>;
}
