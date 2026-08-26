import { readFileSync } from "node:fs";

import { createExternalShadowServer } from "./external_server.js";

const host = process.env.PWC_EXTERNAL_PI_HOST ?? "127.0.0.1";
const port = Number(process.env.PWC_EXTERNAL_PI_PORT ?? "8766");
const token = process.env.PWC_EXTERNAL_PI_TOKEN ?? "";
const maximumConcurrent = Number(process.env.PWC_EXTERNAL_PI_MAX_SESSIONS ?? "8");
const promptPath = process.env.PWC_EXTERNAL_PI_PROMPT_PATH ?? "";
const toolNamesValue = process.env.PWC_EXTERNAL_PI_TOOL_NAMES ?? "";

if (host !== "127.0.0.1" && host !== "::1") {
  throw new Error("External shadow worker must bind to loopback");
}
if (!Number.isInteger(port) || port < 1 || port > 65_535) {
  throw new Error("External shadow worker port is invalid");
}

if (!promptPath) throw new Error("External shadow worker prompt path is missing");
const toolNames = JSON.parse(toolNamesValue) as unknown;
if (!Array.isArray(toolNames) || toolNames.some((name) => typeof name !== "string")) {
  throw new Error("External shadow worker tool profile is invalid");
}

createExternalShadowServer({
  token,
  maximumConcurrent,
  profile: { prompt: readFileSync(promptPath, "utf8"), tool_names: toolNames },
}).listen(port, host);
