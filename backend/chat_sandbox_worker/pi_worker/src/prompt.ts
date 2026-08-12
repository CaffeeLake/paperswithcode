import { readFile } from "node:fs/promises";

const DATE_SENTINEL = "2000-01-01";
const MODEL_SENTINEL = "__PWC_SELECTED_MODEL__";
const USER_SENTINEL = "__PWC_HF_USERNAME__";

export async function renderPrompt(options: {
  model: string;
  hfUsername: string;
  webSearchEnabled: boolean;
  assetPath?: string;
}): Promise<string> {
  const source = await readFile(options.assetPath ?? "/opt/pwc/pi-system-prompt.txt", "utf8");
  const date = new Date().toISOString().slice(0, 10);
  return source
    .replace(DATE_SENTINEL, date)
    .replace(MODEL_SENTINEL, options.model)
    .replace(USER_SENTINEL, options.hfUsername)
    .replace('"web_search_enabled":false', `"web_search_enabled":${String(options.webSearchEnabled)}`);
}
