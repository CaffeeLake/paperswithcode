import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { loadPromptAsset, renderPrompt } from "../src/prompt.js";

test("loads the immutable external-worker prompt path from the launcher environment", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "pwc-prompt-"));
  const promptPath = path.join(directory, "pi-system-prompt.txt");
  const previous = process.env.PWC_EXTERNAL_PI_PROMPT_PATH;
  await writeFile(promptPath, "immutable external prompt", "utf8");
  process.env.PWC_EXTERNAL_PI_PROMPT_PATH = promptPath;
  try {
    assert.equal(await loadPromptAsset(), "immutable external prompt");
  } finally {
    if (previous === undefined) delete process.env.PWC_EXTERNAL_PI_PROMPT_PATH;
    else process.env.PWC_EXTERNAL_PI_PROMPT_PATH = previous;
    await rm(directory, { recursive: true });
  }
});

test("renders the trusted reader-mode metadata independently of paper evidence", async () => {
  const source = [
    "system reader-v1",
    '<turn_metadata>{"web_search_enabled":false,"reader_mode":false}</turn_metadata>',
  ].join("\n");

  const prompt = await renderPrompt({
    model: "model-a",
    hfUsername: "reviewer",
    webSearchEnabled: false,
    readerMode: true,
    source,
  });

  assert.match(prompt, /"reader_mode":true/);
  assert.doesNotMatch(prompt, /"reader_mode":false/);
});

test("replaces the baked task catalog with the live catalog", async () => {
  const source = [
    "before",
    "<!-- PWC_TASK_CATALOG_START -->",
    "stale task catalog",
    "<!-- PWC_TASK_CATALOG_END -->",
    "after",
  ].join("\n");

  const prompt = await renderPrompt({
    model: "model-a",
    hfUsername: "reviewer",
    webSearchEnabled: false,
    readerMode: false,
    taskCatalog: "## Complete live task lookup index\n\n- `text-reranking` — Text Reranking",
    source,
  });

  assert.doesNotMatch(prompt, /stale task catalog/);
  assert.match(prompt, /`text-reranking` — Text Reranking/);
});

test("keeps the shared paper prompt behind the trusted paper flag", async () => {
  const source = [
    "before",
    "## Private paper authoring (paper-v1)",
    "paper-specific instructions",
    "## Task",
    "after",
  ].join("\n");

  const disabled = await renderPrompt({
    model: "model-a", hfUsername: "reviewer", webSearchEnabled: false, readerMode: false, source,
  });
  const enabled = await renderPrompt({
    model: "model-a", hfUsername: "reviewer", webSearchEnabled: false, readerMode: false,
    paperArtifactsEnabled: true, paperGuide: "guide", source,
  });

  assert.doesNotMatch(disabled, /paper-specific instructions/);
  assert.match(enabled, /paper-specific instructions/);
});
