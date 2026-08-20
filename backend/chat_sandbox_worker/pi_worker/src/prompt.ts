import { readFile } from "node:fs/promises";

const DATE_SENTINEL = "2000-01-01";
const MODEL_SENTINEL = "__PWC_SELECTED_MODEL__";
const USER_SENTINEL = "__PWC_HF_USERNAME__";

export async function renderPrompt(options: {
  model: string;
  hfUsername: string;
  webSearchEnabled: boolean;
  readerMode: boolean;
  posterlyEnabled?: boolean;
  assetPath?: string;
  source?: string;
}): Promise<string> {
  const source = options.source ?? await loadPromptAsset(options.assetPath);
  const date = new Date().toISOString().slice(0, 10);
  return source
    .replace(DATE_SENTINEL, date)
    .replace(MODEL_SENTINEL, options.model)
    .replace(USER_SENTINEL, options.hfUsername)
    .replace('"web_search_enabled":false', `"web_search_enabled":${String(options.webSearchEnabled)}`)
    .replace('"reader_mode":false', `"reader_mode":${String(options.readerMode)}`)
    .replace('"posterly_enabled":false', `"posterly_enabled":${String(options.posterlyEnabled === true)}`);
}

export async function loadPromptAsset(assetPath?: string): Promise<string> {
  return readFile(assetPath ?? "/opt/pwc/pi-system-prompt.txt", "utf8");
}
