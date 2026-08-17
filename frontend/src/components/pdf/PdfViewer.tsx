import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { Document, Page } from "react-pdf";
import type { PDFDocumentProxy, TextItem } from "pdfjs-dist/types/src/display/api";
import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";

import { assertPdfWorkerConfigured } from "@/lib/pdf";
import { PdfToolbar } from "./PdfToolbar";

interface PdfViewerProps {
  url: string;
  paperKey: string;
  initialPage?: number;
  resizeActive?: boolean;
  onPageChange?: (page: number) => void;
}

function pdfErrorMessage(error: Error): string {
  const message = error.message.toLowerCase();
  if (message.includes("password")) return "This PDF is encrypted and cannot be opened in the reader.";
  if (message.includes("worker")) return "The PDF renderer could not start.";
  if (message.includes("invalid") || message.includes("format")) return "The source returned an invalid or unsupported PDF.";
  if (message.includes("cors") || message.includes("fetch") || message.includes("network")) return "The PDF source could not be loaded in this browser.";
  return "The PDF could not be loaded from its source.";
}

function LazyPdfPage({ page, width }: { page: number; width: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(page <= 2);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), {
      rootMargin: "120% 0px",
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return <div ref={ref} className="pdf-page" data-page={page} style={{ minHeight: Math.round(width * 1.35) }}>
    {visible && <Page
      pageNumber={page}
      width={width}
      devicePixelRatio={Math.min(window.devicePixelRatio || 1, 2)}
      renderTextLayer
      renderAnnotationLayer
      loading={null}
    />}
  </div>;
}

export function PdfViewer({
  url,
  paperKey,
  initialPage = 1,
  resizeActive = false,
  onPageChange,
}: PdfViewerProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const documentRef = useRef<PDFDocumentProxy | null>(null);
  const searchGeneration = useRef(0);
  const [retry, setRetry] = useState(0);
  const [pages, setPages] = useState(0);
  const [page, setPage] = useState(initialPage);
  const [fitWidth, setFitWidth] = useState(700);
  const [displayWidth, setDisplayWidth] = useState(700);
  const [zoom, setZoom] = useState(1);
  const [error, setError] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [matches, setMatches] = useState<number[]>([]);
  const [activeMatch, setActiveMatch] = useState(0);
  const pageWidth = Math.max(240, Math.round(fitWidth * zoom));

  useEffect(() => {
    assertPdfWorkerConfigured();
  }, []);

  useEffect(() => {
    setPages(0);
    setPage(initialPage);
    setZoom(1);
    setError("");
    setSearchQuery("");
    setMatches([]);
  }, [initialPage, paperKey, retry]);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    const update = () => {
      const nextWidth = Math.max(240, element.clientWidth - 10);
      setDisplayWidth(nextWidth);
      if (!resizeActive) setFitWidth(nextWidth);
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [resizeActive]);

  const liveResizeScale = resizeActive ? displayWidth / fitWidth : 1;

  const setCurrentPage = useCallback((next: number) => {
    const bounded = Math.max(1, Math.min(pages || 1, next));
    setPage(bounded);
    onPageChange?.(bounded);
  }, [onPageChange, pages]);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element || !pages) return;
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const center = element.getBoundingClientRect().top + element.clientHeight / 2;
        let bestPage = page;
        let bestDistance = Number.POSITIVE_INFINITY;
        element.querySelectorAll<HTMLElement>("[data-page]").forEach((candidate) => {
          const rect = candidate.getBoundingClientRect();
          const distance = center >= rect.top && center <= rect.bottom
            ? 0
            : Math.min(Math.abs(center - rect.top), Math.abs(center - rect.bottom));
          if (distance < bestDistance) {
            bestDistance = distance;
            bestPage = Number(candidate.dataset.page);
          }
        });
        if (bestPage !== page) setCurrentPage(bestPage);
      });
    };
    element.addEventListener("scroll", update, { passive: true });
    update();
    return () => {
      element.removeEventListener("scroll", update);
      cancelAnimationFrame(frame);
    };
  }, [page, pageWidth, pages, setCurrentPage]);

  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "f") {
        event.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  }, []);

  useEffect(() => {
    const pdf = documentRef.current;
    const query = searchQuery.trim().toLocaleLowerCase();
    const generation = ++searchGeneration.current;
    if (!pdf || !query) {
      setMatches([]);
      setActiveMatch(0);
      setSearching(false);
      return;
    }
    setSearching(true);
    const timer = window.setTimeout(() => void (async () => {
      const found: number[] = [];
      for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
        if (searchGeneration.current !== generation) return;
        const pdfPage = await pdf.getPage(pageNumber);
        const content = await pdfPage.getTextContent();
        const text = content.items.map((item) => "str" in item ? (item as TextItem).str : "").join(" ").toLocaleLowerCase();
        let offset = 0;
        while ((offset = text.indexOf(query, offset)) >= 0) {
          found.push(pageNumber);
          offset += Math.max(1, query.length);
        }
      }
      if (searchGeneration.current === generation) {
        setMatches(found);
        setActiveMatch(0);
        setSearching(false);
        if (found[0]) jumpToPage(found[0]);
      }
    })().catch(() => {
      if (searchGeneration.current === generation) setSearching(false);
    }), 180);
    return () => window.clearTimeout(timer);
    // jumpToPage deliberately reads the current mounted scroll surface.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery, pages]);

  const jumpToPage = (next: number) => {
    const bounded = Math.max(1, Math.min(pages || 1, next));
    scrollRef.current?.querySelector<HTMLElement>(`[data-page="${bounded}"]`)?.scrollIntoView({ block: "start" });
    setCurrentPage(bounded);
  };
  const navigateMatch = (direction: 1 | -1) => {
    if (!matches.length) return;
    const next = (activeMatch + direction + matches.length) % matches.length;
    setActiveMatch(next);
    jumpToPage(matches[next]);
  };
  const pageNumbers = useMemo(() => Array.from({ length: pages }, (_, index) => index + 1), [pages]);

  return <div ref={rootRef} className="pdf-viewer">
    <PdfToolbar
      page={page}
      pages={pages}
      zoomPercent={Math.round(zoom * 100)}
      searchOpen={searchOpen}
      searchQuery={searchQuery}
      searchMatch={activeMatch}
      searchCount={matches.length}
      searching={searching}
      originalUrl={url}
      onPage={jumpToPage}
      onZoomIn={() => setZoom((value) => Math.min(3, value + 0.15))}
      onZoomOut={() => setZoom((value) => Math.max(0.5, value - 0.15))}
      onFitWidth={() => setZoom(1)}
      onToggleSearch={() => setSearchOpen((value) => !value)}
      onSearchQuery={setSearchQuery}
      onSearch={navigateMatch}
    />
    <div ref={scrollRef} className="pdf-scroll" role="region" aria-label="Paper PDF">
      {error ? <div className="pdf-error" role="alert">
        <p>{error}</p>
        <div><button type="button" onClick={() => setRetry((value) => value + 1)}>Retry</button> <a href={url} target="_blank" rel="noopener noreferrer">Open original PDF</a></div>
      </div> : <Document
        key={`${paperKey}-${retry}`}
        file={url}
        loading={<div className="pdf-loading" role="status">Loading paper…</div>}
        onLoadSuccess={(pdf) => {
          documentRef.current = pdf;
          setPages(pdf.numPages);
          setError("");
          const restoredPage = Math.max(1, Math.min(pdf.numPages, initialPage));
          if (restoredPage > 1) {
            requestAnimationFrame(() => requestAnimationFrame(() => {
              scrollRef.current?.querySelector<HTMLElement>(`[data-page="${restoredPage}"]`)?.scrollIntoView({ block: "start" });
              setPage(restoredPage);
              onPageChange?.(restoredPage);
            }));
          }
        }}
        onLoadError={(loadError) => setError(pdfErrorMessage(loadError))}
        externalLinkTarget="_blank"
      >
        <div
          className="pdf-pages"
          style={{ "--pdf-live-scale": liveResizeScale } as CSSProperties}
        >
          {pageNumbers.map((pageNumber) => <LazyPdfPage key={pageNumber} page={pageNumber} width={pageWidth} />)}
        </div>
      </Document>}
    </div>
  </div>;
}
