import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { PaperCard } from "@/components";
import { PaperFeedFilters } from "@/components/PaperFeedFilters";
import { ArrowUpIcon } from "@/components/chat/icons";
import ModelPicker from "@/components/chat/ModelPicker";
import { apiClient } from "@/lib/api";
import { isChatEnabled } from "@/lib/apiUrl";
import { queueChatLaunch } from "@/lib/chatLaunch";
import { SUGGESTED_CHAT_PROMPTS } from "@/lib/chatPrompts";
import { DEFAULT_CHAT_MODEL, FALLBACK_CHAT_MODELS } from "@/lib/chatSessions";
import { displayTaskName, transformPaperForCard } from "@/lib/transform";
import { useInfinitePapers } from "@/hooks/usePapers";
import { useIntersectionObserver } from "@/hooks/useIntersectionObserver";
import { PERIODS, type Period } from "@/hooks/usePeriodFilter";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useQuery } from "@tanstack/react-query";

type OrderBy = "trending" | "date_published" | "citation_count";
type TimeWindow = "today" | "week" | "month" | "all_time";

const SORT_OPTIONS: Array<[OrderBy, string]> = [
  ["trending", "trending"],
  ["date_published", "newest"],
  ["citation_count", "most cited"],
];

const PERIOD_TO_TIME: Record<Period, TimeWindow> = {
  Today: "today",
  "This Week": "week",
  "This Month": "month",
  "All Time": "all_time",
};

const TIME_TO_PERIOD: Record<TimeWindow, Period> = {
  today: "Today",
  week: "This Week",
  month: "This Month",
  all_time: "All Time",
};

const PLACEHOLDER_TYPE_MS = 45;
const PLACEHOLDER_HOLD_MS = 1_800;
const PLACEHOLDER_ERASE_MS = 25;
const PLACEHOLDER_GAP_MS = 350;

const useRotatingChatPlaceholder = (active: boolean) => {
  const [placeholder, setPlaceholder] = useState(SUGGESTED_CHAT_PROMPTS[0].slice(0, 1));

  useEffect(() => {
    if (!active) return;

    if (window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches) {
      setPlaceholder(SUGGESTED_CHAT_PROMPTS[0]);
      return;
    }

    let promptIndex = 0;
    let characterIndex = 1;
    let erasing = false;
    let timer: number;
    setPlaceholder(SUGGESTED_CHAT_PROMPTS[0].slice(0, characterIndex));

    const tick = () => {
      const prompt = SUGGESTED_CHAT_PROMPTS[promptIndex];

      if (!erasing) {
        characterIndex += 1;
        setPlaceholder(prompt.slice(0, characterIndex));
        if (characterIndex === prompt.length) {
          erasing = true;
          timer = window.setTimeout(tick, PLACEHOLDER_HOLD_MS);
          return;
        }
        timer = window.setTimeout(tick, PLACEHOLDER_TYPE_MS);
        return;
      }

      characterIndex -= 1;
      setPlaceholder(prompt.slice(0, characterIndex));
      if (characterIndex === 0) {
        erasing = false;
        promptIndex = (promptIndex + 1) % SUGGESTED_CHAT_PROMPTS.length;
        timer = window.setTimeout(tick, PLACEHOLDER_GAP_MS);
        return;
      }
      timer = window.setTimeout(tick, PLACEHOLDER_ERASE_MS);
    };

    timer = window.setTimeout(tick, PLACEHOLDER_TYPE_MS);
    return () => window.clearTimeout(timer);
  }, [active]);

  return placeholder;
};

const parseOrderBy = (value: string | null): OrderBy => {
  if (value === "trending" || value === "date_published" || value === "citation_count") {
    return value;
  }
  return "trending";
};

const parseTime = (value: string | null): TimeWindow => {
  if (value === "today" || value === "week" || value === "month" || value === "all_time") {
    return value;
  }
  return "all_time";
};

// Inline "ask the assistant" box between the feed title and the paper list.
// Submitting hands the question off to the dedicated chat page.
export const AskAssistant: React.FC = () => {
  const navigate = useNavigate();
  const [question, setQuestion] = useState("");
  const [selectedModel, setSelectedModel] = useState(DEFAULT_CHAT_MODEL);
  const placeholder = useRotatingChatPlaceholder(!question);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
    }
  }, [question]);

  const submit = (prompt = question) => {
    const q = prompt.trim();
    if (!q) return;
    queueChatLaunch(q, selectedModel);
    navigate("/chat");
  };

  return (
    <div className="ask-home">
      <textarea
        ref={ref}
        rows={1}
        value={question}
        placeholder={placeholder}
        aria-label="Ask the assistant"
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
      />
      <div className="ask-home-foot">
        <div className="ask-home-provider-tools">
          <ModelPicker
            models={FALLBACK_CHAT_MODELS}
            selectedModel={selectedModel}
            onModelChange={setSelectedModel}
          />
          <span className="ask-home-hint">
            Via 🤗{" "}
            <a
              href="https://huggingface.co/docs/inference-providers/en/index"
              target="_blank"
              rel="noreferrer"
            >
              Inference Providers
            </a>
          </span>
        </div>
        <button
          type="button"
          className={`chat-send${question.trim() ? " chat-send-on" : ""}`}
          onClick={() => submit()}
          disabled={!question.trim()}
          aria-label="Ask the assistant"
        >
          <ArrowUpIcon />
        </button>
      </div>
    </div>
  );
};

const FeedView: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const orderBy = parseOrderBy(searchParams.get("order_by"));
  const timeWindow = parseTime(searchParams.get("time"));
  const hasCode = searchParams.get("has_code") === "true";
  const hasHfArtifacts = searchParams.get("has_hf_artifacts") === "true";
  const period = TIME_TO_PERIOD[timeWindow];

  const setOrderBy = (nextOrderBy: OrderBy) => {
    const next = new URLSearchParams(searchParams);
    next.set("order_by", nextOrderBy);
    setSearchParams(next);
  };

  const setTimeWindow = (nextPeriod: Period) => {
    const next = new URLSearchParams(searchParams);
    next.set("time", PERIOD_TO_TIME[nextPeriod]);
    setSearchParams(next);
  };

  const setHasCode = (active: boolean) => {
    const next = new URLSearchParams(searchParams);
    if (active) next.set("has_code", "true");
    else next.delete("has_code");
    setSearchParams(next);
  };

  const setHasHfArtifacts = (active: boolean) => {
    const next = new URLSearchParams(searchParams);
    if (active) next.set("has_hf_artifacts", "true");
    else next.delete("has_hf_artifacts");
    setSearchParams(next);
  };

  // Sidebar: top tasks by paper count.
  const topTasks = useQuery({
    queryKey: ["top-tasks-sidebar"],
    queryFn: () => apiClient.getTopTasks({ limit: 8 }),
    staleTime: 10 * 60 * 1000,
  });

  // Sidebar: tasks whose share of recent papers is rising vs their baseline.
  // Independent of Top Domains; overlapping entries appear in both sections
  // so neither list misrepresents its own signal.
  const trendingTasks = useQuery({
    queryKey: ["trending-tasks-sidebar"],
    queryFn: () => apiClient.getTrendingTasks({ limit: 8, level: 0 }),
    staleTime: 10 * 60 * 1000,
  });

  const infinite = useInfinitePapers({
    page_size: 30,
    order_by: orderBy,
    order_dir: "desc",
    time: timeWindow,
    include_resources: true,
    has_code: hasCode,
    has_hf_artifacts: hasHfArtifacts,
  });

  const cards = useMemo(() => {
    const all = infinite.data?.pages.flatMap((p) => p.results) || [];
    return all.map(transformPaperForCard);
  }, [infinite.data]);

  const { targetRef: sentinelRef, isIntersecting } = useIntersectionObserver({ rootMargin: "400px" });
  useEffect(() => {
    if (isIntersecting && infinite.hasNextPage && !infinite.isFetchingNextPage) {
      infinite.fetchNextPage();
    }
  }, [isIntersecting, infinite.hasNextPage, infinite.isFetchingNextPage]); // eslint-disable-line react-hooks/exhaustive-deps

  const isLoading = infinite.isLoading;
  const error = infinite.error;

  return (
    <div className="page">
      <div className="feed-header">
        <div>
          <h1 className="feed-title">
            Trending <em>Research</em>
          </h1>
          <div className="feed-subtitle">Curated daily from arXiv and Hugging Face</div>
        </div>
      </div>

      <div className="layout-with-sidebar">
        <aside className="sidebar">
          <div className="sidebar-section">
            <div className="sidebar-label">Top Domains</div>
            {topTasks.isLoading && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-5 w-full" />
                ))}
              </div>
            )}
            {topTasks.data?.map((task) => (
              <Link key={task.id} to={`/tasks/${task.slug}`} className="sidebar-link">
                {displayTaskName(task.name, task.slug)}
                {task.paper_count != null && <span className="count">{task.paper_count}</span>}
              </Link>
            ))}
            <Link to="/tasks" className="sidebar-link" style={{ marginTop: 8, fontStyle: "italic" }}>
              all domains →
            </Link>
          </div>

          <div className="sidebar-section">
            <div className="sidebar-label">Trending Domains</div>
            {trendingTasks.isLoading && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-5 w-full" />
                ))}
              </div>
            )}
            {trendingTasks.data?.results?.length === 0 && !trendingTasks.isLoading && (
              <div style={{ fontSize: 12, color: "var(--ink-faint)" }}>
                No domains gaining momentum right now.
              </div>
            )}
            {trendingTasks.data?.results?.map((task) => (
              <Link key={task.id} to={`/tasks/${task.slug}`} className="sidebar-link">
                {displayTaskName(task.name, task.slug)}
                <span className="count">{task.share_lift.toFixed(1)}x</span>
              </Link>
            ))}
          </div>
        </aside>

        <div>
          {isChatEnabled() && <AskAssistant />}

          <div className="sort-bar home-feed-sort-bar">
            <div className="paper-feed-toolbar-controls">
              <div className="sort-options">
                {SORT_OPTIONS.map(([k, l]) => (
                  <button
                    key={k}
                    className={`sort-btn ${orderBy === k ? "active" : ""}`}
                    onClick={() => setOrderBy(k)}
                  >
                    {l}
                  </button>
                ))}
              </div>
              <PaperFeedFilters
                hasCode={hasCode}
                hasHfArtifacts={hasHfArtifacts}
                onHasCodeChange={setHasCode}
                onHasHfArtifactsChange={setHasHfArtifacts}
              />
            </div>
            <div className="sort-options sort-options-time">
              {PERIODS.map((p) => (
                <button
                  key={p}
                  className={`sort-btn sort-btn-time ${period === p ? "active" : ""}`}
                  onClick={() => setTimeWindow(p)}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>

          {error && (
            <Alert variant="destructive" className="mb-4">
              <AlertDescription>Failed to load papers. Please try again.</AlertDescription>
            </Alert>
          )}

          {isLoading ? (
            <div className="paper-list">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="paper-card">
                  <div className="paper-thumb-wrap">
                    <Skeleton className="paper-thumb-skeleton" />
                  </div>
                  <div className="paper-body" style={{ flex: 1, gap: 12 }}>
                    <Skeleton className="h-6 w-3/4" />
                    <Skeleton className="h-4 w-1/2" />
                    <Skeleton className="h-12 w-full" />
                  </div>
                </div>
              ))}
            </div>
          ) : cards.length === 0 ? (
            <div className="no-results">No papers in this window.</div>
          ) : (
            <>
              <div className="paper-list">
                {cards.map((p, i) => (
                  <PaperCard key={p.id} paper={p} rank={i + 1} />
                ))}
              </div>
              <div ref={sentinelRef} style={{ height: 1 }} />
              {infinite.isFetchingNextPage && (
                <div style={{ padding: "20px 0", textAlign: "center", color: "var(--ink-faint)" }}>
                  Loading more…
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default FeedView;
