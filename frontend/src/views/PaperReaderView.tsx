import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { PdfViewer } from "@/components/pdf/PdfViewer";
import { usePaper } from "@/hooks/usePapers";
import { isPaperReaderChatEnabled } from "@/lib/apiUrl";
import { chatApi } from "@/lib/api/chat";
import { safeExternalHref } from "@/lib/safeExternalHref";
import { normalizePaperRouteId } from "@/lib/utils";
import { ChatExperience } from "@/views/ChatView";

const DEFAULT_RATIO = 66;
const RATIO_KEY = "pwc:reader:split-ratio";
const sessionKey = (routeId: string) => `pwc:reader:session:${routeId}`;
const collapsedKey = (routeId: string) => `pwc:reader:assistant-collapsed:${routeId}`;
const pageKey = (routeId: string) => `pwc:reader:page:${routeId}`;

function storedPage(routeId: string): number {
  const value = Number(sessionStorage.getItem(pageKey(routeId)));
  return Number.isInteger(value) && value > 0 ? value : 1;
}

function storedRatio(): number {
  const value = Number(localStorage.getItem(RATIO_KEY));
  return Number.isFinite(value) && value >= 45 && value <= 75 ? value : DEFAULT_RATIO;
}

export function directArxivPdfHref(value: unknown): string | null {
  const href = safeExternalHref(value);
  if (!href) return null;
  const parsed = new URL(href);
  if (
    (parsed.hostname === "arxiv.org" || parsed.hostname === "www.arxiv.org")
    && parsed.pathname.startsWith("/pdf/")
    && parsed.pathname.endsWith(".pdf")
  ) {
    parsed.pathname = parsed.pathname.slice(0, -4);
  }
  return parsed.href;
}

export default function PaperReaderView() {
  const { arxivId: rawRouteId } = useParams<{ arxivId: string }>();
  const routeId = normalizePaperRouteId(rawRouteId ?? "").replace(/v\d+$/i, "");
  const navigate = useNavigate();
  const query = usePaper(routeId, Boolean(routeId));
  const availabilityQuery = useQuery({
    queryKey: ["chatAvailability"],
    queryFn: () => chatApi.getAvailability(),
    refetchInterval: 30000,
    retry: false,
  });
  const paper = query.data;
  const pdfUrl = directArxivPdfHref(paper?.url_pdf);
  const canonicalRoute = paper?.arxiv_id?.replace(/v\d+$/i, "") || routeId;
  const [activeSessionId, setActiveSessionId] = useState<string | undefined>(() => {
    const stored = sessionStorage.getItem(sessionKey(routeId));
    return stored || undefined;
  });
  const [ratio, setRatio] = useState(storedRatio);
  const [collapsed, setCollapsed] = useState(
    () => sessionStorage.getItem(collapsedKey(routeId)) === "1",
  );
  const [mobileTab, setMobileTab] = useState<"paper" | "assistant">("paper");
  const [initialPage, setInitialPage] = useState(() => storedPage(routeId));
  const [workspaceWidth, setWorkspaceWidth] = useState(0);
  const [resizeActive, setResizeActive] = useState(false);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const currentPageRef = useRef(storedPage(routeId));
  const desktopSplit = workspaceWidth > 900 && workspaceWidth >= 840;

  useEffect(() => {
    if (rawRouteId && rawRouteId !== routeId) navigate(`/pdf/${routeId}`, { replace: true });
  }, [navigate, rawRouteId, routeId]);

  useEffect(() => {
    const storedSession = sessionStorage.getItem(sessionKey(routeId));
    setActiveSessionId(storedSession || undefined);
    setCollapsed(sessionStorage.getItem(collapsedKey(routeId)) === "1");
    setMobileTab("paper");
    const nextPage = storedPage(routeId);
    currentPageRef.current = nextPage;
    setInitialPage(nextPage);
  }, [routeId]);

  useLayoutEffect(() => {
    const element = workspaceRef.current;
    if (!element) return;
    const update = () => setWorkspaceWidth(element.clientWidth);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [paper]);

  useEffect(() => {
    if (!paper) return;
    document.title = `${paper.title} — Papers With Code reader`;
    let robots = document.querySelector<HTMLMetaElement>('meta[name="robots"]');
    const createdRobots = !robots;
    if (!robots) {
      robots = document.createElement("meta");
      robots.name = "robots";
      document.head.appendChild(robots);
    }
    const priorRobots = robots.content;
    robots.content = "noindex, nofollow";
    let canonical = document.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    const createdCanonical = !canonical;
    if (!canonical) {
      canonical = document.createElement("link");
      canonical.rel = "canonical";
      document.head.appendChild(canonical);
    }
    const priorCanonical = canonical.href;
    canonical.href = `${window.location.origin}/paper/${canonicalRoute}`;
    return () => {
      document.title = "Papers With Code";
      if (createdRobots) robots?.remove(); else if (robots) robots.content = priorRobots;
      if (createdCanonical) canonical?.remove(); else if (canonical) canonical.href = priorCanonical;
    };
  }, [canonicalRoute, paper]);

  const clampRatio = useCallback((next: number) => {
    if (!workspaceWidth) return Math.max(45, Math.min(75, next));
    const minimumPdf = 480 / workspaceWidth * 100;
    const maximumPdf = 100 - 360 / workspaceWidth * 100;
    return Math.max(minimumPdf, Math.min(maximumPdf, next));
  }, [workspaceWidth]);

  useEffect(() => setRatio((value) => clampRatio(value)), [clampRatio]);

  const setSavedRatio = (next: number) => {
    const bounded = clampRatio(next);
    setRatio(bounded);
    localStorage.setItem(RATIO_KEY, String(bounded));
  };
  const resizeFromPointer = (clientX: number) => {
    const rect = workspaceRef.current?.getBoundingClientRect();
    if (!rect) return;
    setSavedRatio((clientX - rect.left) / rect.width * 100);
  };
  const pointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    dragging.current = true;
    setResizeActive(true);
    event.currentTarget.setPointerCapture(event.pointerId);
    resizeFromPointer(event.clientX);
  };
  const finishResize = () => {
    dragging.current = false;
    setResizeActive(false);
  };
  const setAssistantCollapsed = (next: boolean) => {
    setCollapsed(next);
    sessionStorage.setItem(collapsedKey(routeId), next ? "1" : "0");
  };
  const selectSession = (id: string) => {
    setActiveSessionId(id);
    sessionStorage.setItem(sessionKey(routeId), id);
  };
  const newChat = () => {
    setActiveSessionId(undefined);
    sessionStorage.removeItem(sessionKey(routeId));
  };

  const assistantEnabled = isPaperReaderChatEnabled()
    && availabilityQuery.data?.paper_reader_chat_enabled !== false;
  const assistant = paper && assistantEnabled ? <ChatExperience
    mode="paper"
    routeSessionId={activeSessionId}
    primaryPaper={{ id: paper.id, routeId: canonicalRoute, title: paper.title }}
    currentPage={() => currentPageRef.current}
    onSessionId={selectSession}
    onReaderSubmit={() => setMobileTab("assistant")}
    onReaderNewChat={newChat}
  /> : <div className="reader-chat-unavailable">Assistant is not enabled for this preview.</div>;

  if (query.isLoading) return <div className="reader-status" role="status">Loading paper…</div>;
  if (query.error || !paper) return <div className="reader-status" role="alert"><p>Paper not found.</p><Link to="/papers">Browse papers</Link></div>;
  if (availabilityQuery.data?.native_pdf_reader_enabled === false) return <div className="reader-status" role="alert"><p>The native reader is currently unavailable.</p><Link to={`/paper/${canonicalRoute}`}>Back to paper</Link></div>;
  if (paper.source !== "arxiv" || !pdfUrl) return <div className="reader-status" role="alert"><p>Native reading is unavailable for this resource.</p><Link to={`/paper/${canonicalRoute}`}>Back to paper</Link></div>;

  return <div className="paper-reader-shell">
    {!desktopSplit && <div className="reader-tabs" role="tablist" aria-label="Reader panels">
      <button type="button" role="tab" aria-selected={mobileTab === "paper"} onClick={() => setMobileTab("paper")}>Paper</button>
      <button type="button" role="tab" aria-selected={mobileTab === "assistant"} onClick={() => setMobileTab("assistant")}>Assistant</button>
    </div>}
    <div ref={workspaceRef} className={`reader-workspace${desktopSplit ? " is-desktop" : " is-tabs"}${collapsed ? " is-assistant-collapsed" : ""}`}>
      <section
        className={`reader-paper-pane${!desktopSplit && mobileTab !== "paper" ? " is-hidden" : ""}`}
        style={desktopSplit ? { width: collapsed ? "100%" : `${ratio}%` } : undefined}
        role="tabpanel"
        aria-label="Paper"
        aria-hidden={!desktopSplit && mobileTab !== "paper"}
      >
        <PdfViewer
          url={pdfUrl}
          paperKey={canonicalRoute}
          paperTitle={paper.title}
          paperHref={`/paper/${canonicalRoute}`}
          initialPage={initialPage}
          resizeActive={resizeActive}
          onPageChange={(page) => {
            currentPageRef.current = page;
            sessionStorage.setItem(pageKey(routeId), String(page));
          }}
        />
      </section>
      {desktopSplit && !collapsed && <div
        className="reader-resize-handle"
        role="separator"
        aria-label="Resize paper and Assistant panels"
        aria-orientation="vertical"
        aria-valuemin={45}
        aria-valuemax={75}
        aria-valuenow={Math.round(ratio)}
        tabIndex={0}
        onPointerDown={pointerDown}
        onPointerMove={(event) => { if (dragging.current) resizeFromPointer(event.clientX); }}
        onPointerUp={finishResize}
        onPointerCancel={finishResize}
        onLostPointerCapture={finishResize}
        onDoubleClick={() => setSavedRatio(DEFAULT_RATIO)}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
            event.preventDefault();
            setSavedRatio(ratio + (event.key === "ArrowRight" ? 2 : -2));
          }
          if (event.key === "Home") setSavedRatio(45);
          if (event.key === "End") setSavedRatio(75);
        }}
      ><button type="button" onClick={() => setSavedRatio(DEFAULT_RATIO)} title="Reset panel sizes" aria-label="Reset panel sizes">·</button></div>}
      <aside
        className={`reader-assistant-pane${(!desktopSplit && mobileTab !== "assistant") || collapsed ? " is-hidden" : ""}`}
        style={desktopSplit ? { width: collapsed ? 0 : `${100 - ratio}%` } : undefined}
        role="tabpanel"
        aria-label="Assistant"
        aria-hidden={(!desktopSplit && mobileTab !== "assistant") || collapsed}
      >{assistant}</aside>
      {desktopSplit && <button type="button" className="reader-collapse-assistant" onClick={() => setAssistantCollapsed(!collapsed)}>{collapsed ? "Assistant" : "Hide Assistant"}</button>}
    </div>
  </div>;
}
