import type { Evaluation } from "@/lib/api/evaluations.types";

export interface LeaderboardEvaluationVisibility {
  visible: Evaluation[];
  hiddenClosed: Evaluation[];
  topHiddenClosed: Evaluation | null;
}

export function selectLeaderboardEvaluations(
  evaluations: Evaluation[] | undefined,
  taskId: string | null | undefined,
  hideClosedSource: boolean,
): LeaderboardEvaluationVisibility {
  const current = taskId
    ? (evaluations ?? []).filter((evaluation) => evaluation.task_id === taskId)
    : evaluations ?? [];
  const hiddenClosed = current.filter((evaluation) => evaluation.is_open === false);
  const topHiddenClosed = hiddenClosed.reduce<Evaluation | null>((best, evaluation) => {
    if (!best) return evaluation;
    return (evaluation.best_rank ?? Number.POSITIVE_INFINITY) <
      (best.best_rank ?? Number.POSITIVE_INFINITY)
      ? evaluation
      : best;
  }, null);

  return {
    visible: hideClosedSource
      ? current.filter((evaluation) => evaluation.is_open !== false)
      : current,
    hiddenClosed,
    topHiddenClosed,
  };
}
