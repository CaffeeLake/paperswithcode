import React from "react";

import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import type { ChatCitation } from "@/lib/chat";

const isCoarsePointer = (): boolean =>
  typeof window.matchMedia === "function" &&
  window.matchMedia("(hover: none), (pointer: coarse)").matches;

function hostname(value: string): string {
  try {
    return new URL(value).hostname.replace(/^www\./, "");
  } catch {
    return "Web source";
  }
}

const WebPreviewCard: React.FC<{ citation: ChatCitation }> = ({ citation }) => {
  const [imageFailed, setImageFailed] = React.useState(false);
  const [faviconFailed, setFaviconFailed] = React.useState(false);
  const imageUrl = citation.thumbnail_url;
  const faviconUrl = citation.favicon_url;

  return (
    <div className="web-preview-card">
      {imageUrl && !imageFailed && (
        <img
          className="web-preview-image"
          data-testid="web-preview-image"
          src={imageUrl}
          alt=""
          loading="eager"
          decoding="async"
          referrerPolicy="no-referrer"
          onError={() => setImageFailed(true)}
        />
      )}
      <div className="web-preview-meta">
        <div className="web-preview-source">
          {faviconUrl && !faviconFailed && (
            <img
              src={faviconUrl}
              alt=""
              loading="eager"
              decoding="async"
              referrerPolicy="no-referrer"
              onError={() => setFaviconFailed(true)}
            />
          )}
          <span>{hostname(citation.url ?? "")}</span>
          {citation.published && (
            <>
              <span aria-hidden="true">·</span>
              <time>{citation.published.slice(0, 10)}</time>
            </>
          )}
        </div>
        <strong>{citation.title}</strong>
        {citation.excerpt && (
          <p>{citation.excerpt.replace(/\s+/g, " ").trim()}</p>
        )}
      </div>
    </div>
  );
};

export const WebPreviewLink: React.FC<{
  citation: ChatCitation;
  children: React.ReactNode;
}> = ({ citation, children }) => {
  const [open, setOpen] = React.useState(false);
  const href = citation.url ?? "";

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
          href={href}
          className="chat-web-citation"
          target="_blank"
          rel="noopener noreferrer"
        >
          {children}
        </a>
      </HoverCardTrigger>
      <HoverCardContent
        className="web-preview-pop"
        side="bottom"
        align="start"
        collisionPadding={12}
      >
        <WebPreviewCard citation={citation} />
      </HoverCardContent>
    </HoverCard>
  );
};
