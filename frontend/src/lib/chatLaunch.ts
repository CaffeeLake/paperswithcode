export const CHAT_DRAFT_KEY = "pwc:chat-oauth-draft";
export const CHAT_MODEL_KEY = "pwc:chat-oauth-model";
export const CHAT_AUTO_SEND_KEY = "pwc:chat-oauth-auto-send";

export interface QueuedChatLaunch {
  prompt: string;
  model: string | null;
}

/**
 * Preserve a prompt while the chat route lazy-loads or completes OAuth.
 * The chat page clears it only after handing it to the streaming client.
 */
export function queueChatLaunch(
  prompt: string,
  model?: string,
  options: { autoSend?: boolean } = {},
): void {
  const question = prompt.trim();
  if (!question) return;
  sessionStorage.setItem(CHAT_DRAFT_KEY, question);
  if (options.autoSend === false) sessionStorage.removeItem(CHAT_AUTO_SEND_KEY);
  else sessionStorage.setItem(CHAT_AUTO_SEND_KEY, "1");
  if (model) sessionStorage.setItem(CHAT_MODEL_KEY, model);
  else sessionStorage.removeItem(CHAT_MODEL_KEY);
}

export function readQueuedChatLaunch(): QueuedChatLaunch | null {
  if (typeof window === "undefined") return null;
  if (sessionStorage.getItem(CHAT_AUTO_SEND_KEY) !== "1") return null;
  const prompt = sessionStorage.getItem(CHAT_DRAFT_KEY)?.trim();
  if (!prompt) return null;
  return { prompt, model: sessionStorage.getItem(CHAT_MODEL_KEY) };
}

export function clearQueuedChatLaunch(): void {
  sessionStorage.removeItem(CHAT_DRAFT_KEY);
  sessionStorage.removeItem(CHAT_MODEL_KEY);
  sessionStorage.removeItem(CHAT_AUTO_SEND_KEY);
}
