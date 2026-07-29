import React, { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import Composer from "@/components/chat/Composer";
import { AssistantMessage, UserMessage } from "@/components/chat/ChatMessage";
import { Spinner } from "@/components/chat/icons";
import type { ChatMessage, ChatPaperHit } from "@/lib/chat";
import { queueChatLaunch } from "@/lib/chatLaunch";
import {
  ChatRequestError,
  getSharedChat,
  publicShareToUiMessages,
  type ChatShareDetail,
} from "@/lib/chatSessions";

const SharedTranscript: React.FC<{ detail: ChatShareDetail }> = ({ detail }) => {
  const [messages, setMessages] = useState<ChatMessage[]>(
    () => publicShareToUiMessages(detail),
  );
  const papers = useMemo(() => {
    const result: Record<string, ChatPaperHit> = {};
    for (const message of messages) {
      for (const block of message.blocks ?? []) {
        if (block.kind === "tool") {
          for (const paper of block.results ?? []) result[paper.route_id] = paper;
        }
      }
    }
    return result;
  }, [messages]);
  const toggleBlock = (messageId: string, blockIndex: number) => {
    setMessages((previous) => previous.map((message) => {
      if (message.id !== messageId) return message;
      return {
        ...message,
        blocks: message.blocks?.map((block, index) => index === blockIndex
          && (block.kind === "reasoning" || block.kind === "tool")
          ? { ...block, open: !block.open }
          : block),
      };
    }));
  };

  return (
    <div className="shared-chat-transcript">
      {messages.map((message) => message.role === "user"
        ? <UserMessage key={message.id} id={message.id} text={message.text ?? ""} />
        : <AssistantMessage key={message.id} msg={message} papers={papers} onToggleBlock={toggleBlock} />)}
    </div>
  );
};

const SharedChatView: React.FC = () => {
  const { shareId = "" } = useParams<{ shareId: string }>();
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: ["shared-chat", shareId],
    queryFn: () => getSharedChat(shareId),
    retry: (count, error) => !(error instanceof ChatRequestError && error.status === 404) && count < 1,
  });

  useEffect(() => {
    const previousTitle = document.title;
    const existingRobots = document.head.querySelector<HTMLMetaElement>('meta[name="robots"]');
    const previousRobots = existingRobots?.content;
    const robots = existingRobots ?? document.createElement("meta");
    robots.name = "robots";
    robots.content = "noindex,nofollow";
    if (!existingRobots) document.head.appendChild(robots);
    document.title = "Shared conversation";
    return () => {
      document.title = previousTitle;
      if (existingRobots) existingRobots.content = previousRobots ?? "";
      else robots.remove();
    };
  }, []);

  const launchFreshChat = (prompt: string) => {
    queueChatLaunch(prompt);
    navigate("/chat");
  };
  const missing = query.error instanceof ChatRequestError && query.error.status === 404;

  if (query.isLoading) {
    return <div className="shared-chat-state" role="status"><Spinner /> Loading shared conversation…</div>;
  }
  if (missing) {
    return <div className="shared-chat-state shared-chat-not-found">
      <h1>Shared conversation not found</h1>
      <p>This link is invalid or is no longer available.</p>
    </div>;
  }
  if (query.isError || !query.data) {
    return <div className="shared-chat-state" role="alert">
      <h1>Couldn’t load this conversation</h1>
      <p>Please check your connection and try again.</p>
      <button type="button" onClick={() => void query.refetch()}>Try again</button>
    </div>;
  }

  return (
    <div className="shared-chat-page">
      <div className="shared-chat-content">
        <SharedTranscript key={query.data.updated_at} detail={query.data} />
        <section className="shared-chat-fresh" aria-labelledby="shared-chat-fresh-title">
          <h2 id="shared-chat-fresh-title">Start a new conversation</h2>
          <p>Your new question starts with an empty context.</p>
          <Composer onSend={launchFreshChat} placeholder="Ask a new research question…" />
        </section>
      </div>
    </div>
  );
};

export default SharedChatView;
