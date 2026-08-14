import { describe, expect, it } from "vitest";

import {
  normalizeEvaluationOperations,
  toDirectEvaluationOperations,
  toPendingEvaluationOperations,
  type EditableEvaluationRow,
} from "./evaluationOperations";

const row = (overrides: Partial<EditableEvaluationRow>): EditableEvaluationRow => ({
  task_id: "3",
  dataset_id: "7",
  model_name: " Model ",
  harness: " verified ",
  metric_name: "Accuracy",
  metric_value: "91.2",
  best_rank: "2",
  num_parameters: " 125000 ",
  hf_model_url: " https://huggingface.co/org/model ",
  is_open: true,
  operation: "create",
  ...overrides,
});

describe("evaluation operation normalization", () => {
  it("normalizes create values once and both transports preserve them", () => {
    const canonical = normalizeEvaluationOperations([row({})], () => true);
    const create = canonical[0];
    if (!create || create.kind !== "create") throw new Error("Expected create operation");

    expect(canonical).toEqual([{
      kind: "create",
      data: {
        task_id: 3,
        dataset_id: 7,
        model_name: "Model",
        harness: "verified",
        metrics: { Accuracy: "91.2" },
        best_metric: "Accuracy",
        best_rank: 2,
        num_parameters: 125000,
        hf_model_url: "https://huggingface.co/org/model",
        is_open: true,
      },
    }]);
    expect(toDirectEvaluationOperations(11, canonical)[0]?.payload).toEqual({
      paper_id: 11,
      ...create.data,
    });
    expect(toPendingEvaluationOperations(canonical)[0]).toEqual({
      op: "create",
      data: create.data,
    });
  });

  it("represents update clears as explicit null fields", () => {
    const canonical = normalizeEvaluationOperations([
      row({
        id: "19",
        operation: "update",
        harness: "",
        num_parameters: "",
        hf_model_url: "  ",
      }),
    ], () => true);

    expect(canonical[0]).toMatchObject({
      kind: "update",
      evaluationId: 19,
      data: { harness: null, num_parameters: null, hf_model_url: null },
    });
    expect(toDirectEvaluationOperations(11, canonical)[0]?.payload).toMatchObject({
      harness: null,
      num_parameters: null,
      hf_model_url: null,
    });
    expect(toPendingEvaluationOperations(canonical)[0]).toMatchObject({
      data: { harness: null, num_parameters: null, hf_model_url: null },
    });
  });

  it("clears unsupported harnesses and omits empty create optionals", () => {
    const canonical = normalizeEvaluationOperations([
      row({ operation: "create", harness: "x", num_parameters: "", hf_model_url: "" }),
      row({ id: "20", operation: "update", harness: "x" }),
    ], () => false);

    expect(canonical[0]).not.toHaveProperty("data.harness");
    expect(canonical[0]).not.toHaveProperty("data.num_parameters");
    expect(canonical[0]).not.toHaveProperty("data.hf_model_url");
    expect(canonical[1]).toHaveProperty("data.harness", null);
  });

  it("preserves delete operations and ignores unchanged or incomplete rows", () => {
    const canonical = normalizeEvaluationOperations([
      row({ id: "21", operation: "delete" }),
      row({ id: "22", operation: "unchanged" }),
      row({ operation: "create", metric_value: "" }),
    ], () => true);

    expect(canonical).toEqual([{ kind: "delete", evaluationId: 21 }]);
    expect(toDirectEvaluationOperations(11, canonical)).toEqual([
      { operation: "delete", evaluation_id: 21 },
    ]);
    expect(toPendingEvaluationOperations(canonical)).toEqual([
      { op: "delete", evaluation_id: 21 },
    ]);
  });
});
