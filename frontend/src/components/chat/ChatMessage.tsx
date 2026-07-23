/**
 * Message rendering for the assistant chat: user bubbles plus the assistant's
 * ordered stream blocks — live/collapsed reasoning, `search_papers` tool-call
 * accordions with ranked hits, and the final cited answer.
 */

import React from "react";

import { ChatMarkdown, PaperCitation } from "@/components/chat/ChatMarkdown";
import { CheckIcon, Chevron, SearchIcon, Spinner } from "@/components/chat/icons";
import { authorsLine, excerpt, venueLine } from "@/components/chat/paperDisplay";
import type {
  AnswerBlock,
  ChatMessage as ChatMessageType,
  ChatPaperHit,
  ReasoningBlock,
  ToolBlock,
} from "@/lib/chat";

const Caret: React.FC = () => <span className="chat-caret" />;

const ReasoningBlockView: React.FC<{
  block: ReasoningBlock;
  onToggle: () => void;
}> = ({ block, onToggle }) => {
  if (block.active) {
    return (
      <div className="chat-reason-live">
        <div className="chat-reason-live-head">
          <Spinner /> <span>Thinking…</span>
        </div>
        <div className="chat-reason-live-body">
          {block.text}
          <Caret />
        </div>
      </div>
    );
  }
  return (
    <div className="chat-reason-done">
      <button type="button" className="chat-reason-done-head" onClick={onToggle}>
        <CheckIcon />
        <span>Thought for a few seconds</span>
        <Chevron open={block.open} />
      </button>
      {block.open && <div className="chat-reason-done-body">{block.text}</div>}
    </div>
  );
};

const ToolBlockView: React.FC<{
  block: ToolBlock;
  papers: Record<string, ChatPaperHit>;
  onToggle: () => void;
}> = ({ block, papers, onToggle }) => {
  const running = block.status === "running";
  const query = typeof block.args.query === "string" ? block.args.query : "";
  return (
    <div className={`chat-tool${running ? " chat-tool-running" : ""}`}>
      <button type="button" className="chat-tool-head" onClick={onToggle} disabled={running}>
        <span className="chat-tool-head-left">
          {running ? <Spinner /> : <SearchIcon />}
          <code className="chat-tool-name">{block.name}</code>
          <span className="chat-tool-query">(&quot;{query}&quot;)</span>
        </span>
        <span className="chat-tool-head-right">
          {running ? (
            <span className="chat-tool-status">searching…</span>
          ) : (
            <span className="chat-tool-status">
              {block.hits} results · {block.took_ms} ms
            </span>
          )}
          {!running && <Chevron open={block.open} />}
        </span>
      </button>
      {!running && block.open && (
        <div className="chat-tool-body">
          <div className="chat-tool-args">
            <span className="chat-tool-label">arguments</span>
            <pre>{JSON.stringify(block.args, null, 2)}</pre>
          </div>
          <div className="chat-tool-label chat-tool-results-label">
            returned {block.results?.length ?? 0} papers
          </div>
          <ol className="chat-tool-results">
            {block.results?.map((r) => (
              <li key={r.route_id} className="chat-hit">
                <div className="chat-hit-top">
                  <PaperCitation
                    routeId={r.route_id}
                    paper={papers[r.route_id]}
                    className="chat-hit-title"
                  >
                    {r.title}
                  </PaperCitation>
                </div>
                <div className="chat-hit-meta">
                  {[authorsLine(r.metadata), venueLine(r.metadata)]
                    .filter(Boolean)
                    .join(" · ")}
                </div>
                <div className="chat-hit-snippet">
                  {excerpt(r)}
                  {r.content_truncated && <span className="chat-hit-truncated"> (truncated)</span>}
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
};

const AnswerBlockView: React.FC<{
  block: AnswerBlock;
  papers: Record<string, ChatPaperHit>;
}> = ({ block, papers }) => (
  <div className="chat-answer">
    <ChatMarkdown text={block.text} streaming={!block.done} papers={papers} />
    {!block.done && Boolean(block.text.trim()) && <Caret />}
  </div>
);

export const UserMessage: React.FC<{ text: string }> = ({ text }) => (
  <div className="chat-msg chat-msg-user">
    <div className="chat-bubble">{text}</div>
  </div>
);

export const AssistantMessage: React.FC<{
  msg: ChatMessageType;
  papers: Record<string, ChatPaperHit>;
  onToggleBlock: (messageId: string, blockIndex: number) => void;
}> = ({ msg, papers, onToggleBlock }) => (
  <div className="chat-msg chat-msg-assistant">
    <div className="chat-msg-blocks">
      {msg.streaming && (msg.blocks?.length ?? 0) === 0 && (
        <div className="chat-reason-live-head">
          <Spinner /> <span>Thinking…</span>
        </div>
      )}
      {msg.blocks?.map((b, i) => {
        const key = `${msg.id}-${i}`;
        if (b.kind === "reasoning") {
          return <ReasoningBlockView key={key} block={b} onToggle={() => onToggleBlock(msg.id, i)} />;
        }
        if (b.kind === "tool") {
          return (
            <ToolBlockView key={key} block={b} papers={papers} onToggle={() => onToggleBlock(msg.id, i)} />
          );
        }
        return <AnswerBlockView key={key} block={b} papers={papers} />;
      })}
      {msg.error && <div className="chat-error">The assistant hit an error: {msg.error}</div>}
      {!msg.streaming && msg.finishReason && msg.finishReason !== "success" && (
        <div className="chat-finish-note">
          The assistant stopped early ({msg.finishReason.replace(/_/g, " ")}).
        </div>
      )}
    </div>
  </div>
);
