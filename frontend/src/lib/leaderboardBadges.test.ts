import { describe, expect, it } from "vitest";

import { leaderboardBadgeMarkdown } from "./leaderboardBadges";

describe("leaderboardBadgeMarkdown", () => {
  it("keeps the compatible image URL and uses the durable click target", () => {
    const markdown = leaderboardBadgeMarkdown(
      "2601.21998",
      [
        {
          evaluation_id: "7",
          dataset_name: "Benchmark A",
          dataset_slug: "benchmark-a",
          best_rank: 2,
          best_metric: "Accuracy",
          task_slug: "task",
        },
      ],
    );

    expect(markdown).toBe(
      "[![Papers with Code: #2 on Benchmark A]" +
        "(https://paperswithcode.co/api/v1/papers/2601.21998/leaderboard-badge.svg?eval=7&live=1)]" +
        "(https://paperswithcode.co/api/v1/papers/2601.21998/leaderboard-badge-link?eval=7)",
    );
  });
});
