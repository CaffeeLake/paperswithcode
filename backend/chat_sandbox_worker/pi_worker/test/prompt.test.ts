import assert from "node:assert/strict";
import test from "node:test";

import { renderPrompt } from "../src/prompt.js";

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
