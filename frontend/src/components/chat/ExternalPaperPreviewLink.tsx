import React from "react";

import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import type { ChatCitation } from "@/lib/chat";

const isCoarsePointer = (): boolean =>
  typeof window.matchMedia === "function"
  && window.matchMedia("(hover: none), (pointer: coarse)").matches;

const providerLabel = (provider: ChatCitation["provider"]): string => {
  if (provider === "semantic_scholar") return "Semantic Scholar";
  return "External paper";
};

const ExternalPaperPreviewCard: React.FC<{ citation: ChatCitation }> = ({ citation }) => (
  <div className="external-paper-preview-card">
    <div className="external-paper-preview-source">
      <span>{providerLabel(citation.provider)}</span>
      {citation.published && (
        <>
          <span aria-hidden="true">·</span>
          <time>{citation.published.slice(0, 10)}</time>
        </>
      )}
    </div>
    <strong>{citation.title}</strong>
    {(citation.authors?.length ?? 0) > 0 && (
      <p className="external-paper-preview-authors">{citation.authors?.join(", ")}</p>
    )}
    {citation.excerpt && <p>{citation.excerpt.replace(/\s+/g, " ").trim()}</p>}
    {citation.citation_count !== null && citation.citation_count !== undefined && (
      <span className="external-paper-preview-citations">
        {citation.citation_count.toLocaleString()} citations
      </span>
    )}
  </div>
);

export const ExternalPaperPreviewLink: React.FC<{
  citation: ChatCitation;
  children: React.ReactNode;
}> = ({ citation, children }) => {
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
          href={citation.url ?? ""}
          className="chat-external-paper-citation"
          target="_blank"
          rel="noopener noreferrer"
        >
          {children}
        </a>
      </HoverCardTrigger>
      <HoverCardContent
        className="external-paper-preview-pop"
        side="bottom"
        align="start"
        collisionPadding={12}
      >
        <ExternalPaperPreviewCard citation={citation} />
      </HoverCardContent>
    </HoverCard>
  );
};
