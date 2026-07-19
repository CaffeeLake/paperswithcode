import type { LeaderboardRankSummary } from "@/lib/api";

export type CopyableLeaderboardRank = LeaderboardRankSummary & {
  dataset_slug: string;
  task_slug: string;
};

export function copyableLeaderboardRanks(
  ranks: LeaderboardRankSummary[] | null | undefined,
): CopyableLeaderboardRank[] {
  return (ranks ?? []).filter(
    (rank): rank is CopyableLeaderboardRank => Boolean(rank.dataset_slug && rank.task_slug),
  );
}

export function leaderboardBadgeMarkdown(
  paperId: string,
  ranks: CopyableLeaderboardRank[],
  siteOrigin = "https://paperswithcode.co",
): string {
  return ranks
    .map((rank) => {
      const evaluationId = encodeURIComponent(rank.evaluation_id);
      const badgeUrl = `${siteOrigin}/api/v1/papers/${encodeURIComponent(paperId)}/leaderboard-badge.svg?eval=${evaluationId}&live=1`;
      const query = new URLSearchParams({ task: rank.task_slug, eval: rank.evaluation_id });
      const leaderboardUrl = `${siteOrigin}/benchmark/${encodeURIComponent(rank.dataset_slug)}?${query.toString()}`;
      const placement = rank.best_rank === 1 ? "SOTA" : `#${rank.best_rank}`;
      const alt = `Papers with Code: ${placement} on ${rank.dataset_name}`;
      return `[![${alt}](${badgeUrl})](${leaderboardUrl})`;
    })
    .join("\n");
}
