import React from "react";
import { Github } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import {
  fetchGitHubRepoPreview,
  type GitHubRepo,
  type GitHubRepoPreview,
} from "@/lib/github";
import { preloadImage } from "@/lib/imagePreloader";

const isCoarsePointer = (): boolean =>
  typeof window.matchMedia === "function" &&
  window.matchMedia("(hover: none), (pointer: coarse)").matches;

const GitHubRepoCard: React.FC<{
  repo: GitHubRepo;
  preview?: GitHubRepoPreview;
  unavailable?: boolean;
}> = ({ repo, preview, unavailable }) => {
  const [imageFailed, setImageFailed] = React.useState(false);
  const showAvatar = Boolean(preview?.avatarUrl) && !imageFailed;

  return (
    <div className="github-preview-card">
      {showAvatar ? (
        <img
          className="github-preview-image"
          data-testid="github-preview-image"
          src={preview?.avatarUrl}
          alt=""
          loading="eager"
          decoding="async"
          onError={() => setImageFailed(true)}
        />
      ) : (
        <div className="github-preview-fallback" aria-hidden="true">
          <Github />
        </div>
      )}
      <div className="github-preview-meta">
        <span className="github-preview-kind">GitHub repository</span>
        <strong>{repo.repoId}</strong>
        {preview?.description && (
          <span className="github-preview-description">{preview.description}</span>
        )}
        {preview ? (
          <span className="github-preview-stats">
            {preview.language && <>{preview.language} · </>}
            ★ {preview.stars.toLocaleString()} · ⑂ {preview.forks.toLocaleString()}
            {preview.archived && <> · Archived</>}
          </span>
        ) : (
          <span>{unavailable ? "Preview unavailable" : "Loading preview…"}</span>
        )}
      </div>
    </div>
  );
};

export const GitHubPreviewLink: React.FC<{
  repo: GitHubRepo;
  children: React.ReactNode;
}> = ({ repo, children }) => {
  const [open, setOpen] = React.useState(false);
  const [shouldLoad, setShouldLoad] = React.useState(false);
  const triggerRef = React.useRef<HTMLAnchorElement>(null);
  const warmPreview = React.useCallback(() => setShouldLoad(true), []);
  const query = useQuery({
    queryKey: ["github-repository-preview", repo.repoId.toLowerCase()],
    queryFn: ({ signal }) => fetchGitHubRepoPreview(repo, signal),
    enabled: open || shouldLoad,
    staleTime: 30 * 60 * 1000,
    gcTime: 60 * 60 * 1000,
    retry: false,
  });

  React.useEffect(() => {
    const trigger = triggerRef.current;
    if (!trigger || typeof IntersectionObserver === "undefined") return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        warmPreview();
        observer.disconnect();
      },
      { rootMargin: "200px" },
    );
    observer.observe(trigger);
    return () => observer.disconnect();
  }, [warmPreview]);

  React.useEffect(() => {
    if (query.data?.avatarUrl) void preloadImage(query.data.avatarUrl);
  }, [query.data?.avatarUrl]);

  return (
    <HoverCard
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen || !isCoarsePointer()) setOpen(nextOpen);
      }}
      openDelay={150}
      closeDelay={100}
    >
      <HoverCardTrigger asChild>
        <a
          ref={triggerRef}
          className="chat-github-link"
          href={repo.url}
          target="_blank"
          rel="noopener noreferrer"
          onPointerEnter={warmPreview}
          onFocus={warmPreview}
        >
          <Github aria-hidden="true" />
          {children}
        </a>
      </HoverCardTrigger>
      <HoverCardContent
        className="github-preview-pop"
        side="bottom"
        align="start"
        collisionPadding={12}
      >
        <GitHubRepoCard
          repo={repo}
          preview={query.data}
          unavailable={query.isError}
        />
      </HoverCardContent>
    </HoverCard>
  );
};
