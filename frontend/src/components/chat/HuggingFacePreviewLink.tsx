import React from "react";

import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";

export interface HuggingFaceRepo {
  type: "model" | "dataset";
  repoId: string;
  url: string;
  thumbnailUrl: string;
}

const HUB_HOSTS = new Set(["huggingface.co", "www.huggingface.co"]);
const RESERVED_HUB_ROUTES = new Set([
  "api",
  "blog",
  "chat",
  "collections",
  "docs",
  "enterprise",
  "join",
  "login",
  "models",
  "new",
  "organizations",
  "papers",
  "posts",
  "pricing",
  "search",
  "settings",
  "spaces",
  "tasks",
]);

export function parseHuggingFaceRepoUrl(
  value: string,
): HuggingFaceRepo | null {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return null;
  }
  if (url.protocol !== "https:" || !HUB_HOSTS.has(url.hostname)) return null;

  const parts = url.pathname.split("/").filter(Boolean);
  const type = parts[0] === "datasets" ? "dataset" : "model";
  const repoParts = type === "dataset" ? parts.slice(1) : parts;
  if (
    repoParts.length !== 2 ||
    (type === "model" && RESERVED_HUB_ROUTES.has(repoParts[0])) ||
    repoParts.some((part) => !part || part === "." || part === "..")
  ) {
    return null;
  }

  const repoId = repoParts.join("/");
  const encodedRepoId = repoParts.map(encodeURIComponent).join("/");
  const repoPath =
    type === "dataset" ? `datasets/${encodedRepoId}` : encodedRepoId;
  const thumbnailType = type === "dataset" ? "datasets" : "models";
  return {
    type,
    repoId,
    url: `https://huggingface.co/${repoPath}`,
    thumbnailUrl:
      `https://cdn-thumbnails.huggingface.co/social-thumbnails/` +
      `${thumbnailType}/${encodedRepoId}.png`,
  };
}

const isCoarsePointer = (): boolean =>
  typeof window.matchMedia === "function" &&
  window.matchMedia("(hover: none), (pointer: coarse)").matches;

const HuggingFaceRepoCard: React.FC<{ repo: HuggingFaceRepo }> = ({ repo }) => {
  const [imageFailed, setImageFailed] = React.useState(false);

  return (
    <div className="hf-preview-card">
      {imageFailed ? (
        <div className="hf-preview-fallback" aria-hidden="true">
          🤗
        </div>
      ) : (
        <img
          className="hf-preview-image"
          data-testid="hf-preview-image"
          src={repo.thumbnailUrl}
          alt=""
          loading="lazy"
          decoding="async"
          onError={() => setImageFailed(true)}
        />
      )}
      <div className="hf-preview-meta">
        <span className="hf-preview-kind">
          Hugging Face {repo.type}
        </span>
        <strong>{repo.repoId}</strong>
        <span>huggingface.co</span>
      </div>
    </div>
  );
};

export const HuggingFacePreviewLink: React.FC<{
  repo: HuggingFaceRepo;
  children: React.ReactNode;
}> = ({ repo, children }) => {
  const [open, setOpen] = React.useState(false);

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
          className="chat-paper-link chat-hf-link"
          href={repo.url}
          target="_blank"
          rel="noopener noreferrer"
        >
          {children}
        </a>
      </HoverCardTrigger>
      <HoverCardContent
        className="hf-preview-pop"
        side="bottom"
        align="start"
        collisionPadding={12}
      >
        <HuggingFaceRepoCard repo={repo} />
      </HoverCardContent>
    </HoverCard>
  );
};
