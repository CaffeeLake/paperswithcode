import { useEffect, useState } from "react";

import { PanelIcon, PlusIcon, TrashIcon } from "./icons";
import { canNavigateAwayFromArtifact } from "./useArtifactPanel";
import { type ChatSession, groupSessions } from "@/lib/chatSessions";

interface ChatSessionNavigationProps {
  sessions: ChatSession[];
  activeSessionId?: string;
  loading: boolean;
  error: string;
  open: boolean;
  onClose: () => void;
  onNew: () => void;
  onNavigate: (sessionId: string) => void;
  onRename: (sessionId: string, title: string) => Promise<boolean>;
  onDelete: (sessionId: string) => void;
}

export function ChatSessionNavigation({
  sessions,
  activeSessionId,
  loading,
  error,
  open,
  onClose,
  onNew,
  onNavigate,
  onRename,
  onDelete,
}: ChatSessionNavigationProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const [menu, setMenu] = useState<{ id: string; x: number; y: number } | null>(null);

  useEffect(() => {
    if (!menu) return;
    const close = () => setMenu(null);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("click", close);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("keydown", onKey);
    };
  }, [menu]);

  const beginRename = (session: ChatSession) => {
    setEditingId(session.id);
    setEditingTitle(session.title);
  };
  const saveRename = async (sessionId: string) => {
    const title = editingTitle.trim();
    if (title && await onRename(sessionId, title)) setEditingId(null);
  };
  const openMenu = (id: string, x: number, y: number) => setMenu({ id, x, y });

  return (
    <aside className={`chat-sidebar${open ? "" : " chat-sidebar-closed"}`}>
      <div className="chat-sidebar-top">
        <button type="button" className="chat-new-chat" onClick={() => { if (canNavigateAwayFromArtifact()) onNew(); }}><PlusIcon /> New chat</button>
        <button type="button" className="icon-btn" onClick={onClose} title="Collapse sidebar"><PanelIcon /></button>
      </div>
      <nav className="chat-sessions" aria-label="Chat history">
        {loading && <div className="chat-sessions-empty">Loading chats…</div>}
        {!loading && error && <div className="chat-sessions-empty">{error}</div>}
        {!loading && !error && sessions.length === 0 && (
          <div className="chat-sessions-empty">Conversations you start will show up here.</div>
        )}
        {groupSessions(sessions).map((group) => <div className="chat-session-group" key={group.label}>
          <div className="chat-session-group-label">{group.label}</div>
          {group.items.map((session) => <div
            key={session.id}
            className={`chat-session${session.id === activeSessionId ? " chat-session-active" : ""}`}
            role="button"
            tabIndex={0}
            onClick={() => { if (canNavigateAwayFromArtifact()) onNavigate(session.id); }}
            onKeyDown={(event) => {
              if (event.key === "Enter" && canNavigateAwayFromArtifact()) onNavigate(session.id);
              if (event.key === "F2") beginRename(session);
              if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
                event.preventDefault();
                const rect = event.currentTarget.getBoundingClientRect();
                openMenu(session.id, rect.right - 150, rect.bottom);
              }
            }}
            onContextMenu={(event) => {
              event.preventDefault();
              openMenu(session.id, event.clientX, event.clientY);
            }}
          >
            {editingId === session.id ? <input
              className="chat-session-title-input"
              value={editingTitle}
              autoFocus
              maxLength={80}
              onClick={(event) => event.stopPropagation()}
              onChange={(event) => setEditingTitle(event.target.value)}
              onBlur={() => void saveRename(session.id)}
              onKeyDown={(event) => {
                event.stopPropagation();
                if (event.key === "Enter") void saveRename(session.id);
                if (event.key === "Escape") setEditingId(null);
              }}
            /> : <span className="chat-session-title">{session.title}</span>}
            <button
              type="button"
              className="chat-session-menu"
              aria-label="Chat actions"
              aria-haspopup="menu"
              title="Chat actions"
              onClick={(event) => {
                event.stopPropagation();
                const rect = event.currentTarget.getBoundingClientRect();
                openMenu(session.id, rect.right - 150, rect.bottom);
              }}
            >⋯</button>
            <button
              type="button"
              className="chat-session-delete"
              aria-label="Delete conversation"
              onClick={(event) => {
                event.stopPropagation();
                if (canNavigateAwayFromArtifact()) onDelete(session.id);
              }}
            ><TrashIcon /></button>
          </div>)}
        </div>)}
      </nav>
      {menu && <div
        className="chat-session-context-menu"
        role="menu"
        style={{ left: menu.x, top: menu.y }}
        onClick={(event) => event.stopPropagation()}
      >
        <button type="button" role="menuitem" autoFocus onClick={() => {
          const session = sessions.find((item) => item.id === menu.id);
          if (session) beginRename(session);
          setMenu(null);
        }}>Rename chat</button>
      </div>}
    </aside>
  );
}
