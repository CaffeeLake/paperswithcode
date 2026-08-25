/* eslint-disable react-refresh/only-export-components */
import React from "react";

import { ArtifactPanel } from "./ArtifactPanel";
import { useArtifactPanel } from "./useArtifactPanel";

export type ArtifactWorkspaceVariant = "chat" | "shared" | "reader";

const BOUNDS = {
  chat: { breakpoint: 760, left: 360, right: 360 },
  shared: { breakpoint: 760, left: 360, right: 360 },
  reader: { breakpoint: 1260, left: 840, right: 420 },
} as const;

export function clampArtifactPercent(
  width: number,
  requested: number,
  leftMinimum: number,
  rightMinimum: number,
): number {
  if (!width) return Math.max(25, Math.min(75, requested));
  const lower = Math.max(25, rightMinimum / width * 100);
  const upper = Math.min(75, (width - leftMinimum) / width * 100);
  return Math.max(lower, Math.min(upper, requested));
}

export const ArtifactWorkspace: React.FC<{
  children: React.ReactNode;
  variant: ArtifactWorkspaceVariant;
}> = ({ children, variant }) => {
  const panel = useArtifactPanel();
  const bounds = BOUNDS[variant];
  const hostRef = React.useRef<HTMLDivElement>(null);
  const contentRef = React.useRef<HTMLDivElement>(null);
  const paneRef = React.useRef<HTMLDivElement>(null);
  const handleRef = React.useRef<HTMLDivElement>(null);
  const [width, setWidth] = React.useState(0);
  const draggingRef = React.useRef(false);
  const pendingPercentRef = React.useRef(panel.state.panelPercent);

  React.useLayoutEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const update = () => setWidth(host.clientWidth || window.innerWidth);
    update();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(update);
    observer.observe(host);
    return () => observer.disconnect();
  }, []);

  const docked = panel.state.open && width >= bounds.breakpoint;
  const percent = clampArtifactPercent(
    width,
    panel.state.panelPercent,
    bounds.left,
    bounds.right,
  );
  const canvasLabel = panel.state.selected?.artifact_kind === "latex_paper" ? "paper" : "poster";
  const applyPercent = (next: number) => {
    const bounded = clampArtifactPercent(width, next, bounds.left, bounds.right);
    pendingPercentRef.current = bounded;
    if (contentRef.current) contentRef.current.style.width = `${100 - bounded}%`;
    if (paneRef.current) paneRef.current.style.width = `${bounded}%`;
    handleRef.current?.setAttribute("aria-valuenow", String(Math.round(bounded)));
  };
  const resizeFromPointer = (clientX: number) => {
    const rect = hostRef.current?.getBoundingClientRect();
    if (!rect?.width) return;
    applyPercent((rect.right - clientX) / rect.width * 100);
  };
  const finishResize = () => {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    panel.setPanelPercent(pendingPercentRef.current);
  };

  return <div
    ref={hostRef}
    className={`chat-artifact-workspace chat-artifact-workspace-${variant}${docked ? " has-docked-artifact" : ""}`}
    data-artifact-layout={docked ? "split" : panel.state.open ? "dialog" : "closed"}
  >
    <div
      ref={contentRef}
      className="chat-artifact-workspace-content"
      style={docked ? { width: `${100 - percent}%` } : undefined}
    >{children}</div>
    {docked && <>
      <div
        ref={handleRef}
        className="chat-artifact-resize-handle"
        role="separator"
        aria-label={`Resize conversation and ${canvasLabel} panels`}
        aria-orientation="vertical"
        aria-valuemin={Math.ceil(clampArtifactPercent(width, 0, bounds.left, bounds.right))}
        aria-valuemax={Math.floor(clampArtifactPercent(width, 100, bounds.left, bounds.right))}
        aria-valuenow={Math.round(percent)}
        tabIndex={0}
        onPointerDown={(event) => {
          draggingRef.current = true;
          event.currentTarget.setPointerCapture(event.pointerId);
          resizeFromPointer(event.clientX);
        }}
        onPointerMove={(event) => { if (draggingRef.current) resizeFromPointer(event.clientX); }}
        onPointerUp={finishResize}
        onPointerCancel={finishResize}
        onLostPointerCapture={finishResize}
        onDoubleClick={() => panel.setPanelPercent(55)}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
            event.preventDefault();
            panel.setPanelPercent(clampArtifactPercent(
              width,
              percent + (event.key === "ArrowLeft" ? 2 : -2),
              bounds.left,
              bounds.right,
            ));
          }
          if (event.key === "Home") panel.setPanelPercent(clampArtifactPercent(width, 25, bounds.left, bounds.right));
          if (event.key === "End") panel.setPanelPercent(clampArtifactPercent(width, 75, bounds.left, bounds.right));
        }}
      />
      <div ref={paneRef} className="chat-artifact-workspace-pane" style={{ width: `${percent}%` }}>
        <ArtifactPanel />
      </div>
    </>}
    {panel.state.open && !docked && <ArtifactPanel forceDialog readerFallback={variant === "reader"} />}
  </div>;
};
