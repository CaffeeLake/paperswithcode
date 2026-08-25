/* eslint-disable react-refresh/only-export-components */
import React from "react";

import type { ArtifactBlock } from "@/lib/chat";

export type ArtifactTab = "preview" | "source" | "files";

export interface ArtifactPanelState {
  open: boolean;
  selectedKey: string | null;
  selected: ArtifactBlock | null;
  selectedVersionId: string | null;
  tab: ArtifactTab;
  sourceFile: string | null;
  panelPercent: number;
  requestNonce: number;
  registry: Record<string, ArtifactBlock>;
  autoOpened: Record<string, boolean>;
  manuallyClosed: Record<string, boolean>;
}

type Action =
  | { type: "reset" }
  | { type: "register"; key: string; block: ArtifactBlock; autoOpenOnMount: boolean }
  | { type: "unregister"; key: string }
  | { type: "open"; key: string; block: ArtifactBlock }
  | { type: "close" }
  | { type: "tab"; tab: ArtifactTab }
  | { type: "source"; path: string | null }
  | { type: "version"; versionId: string | null }
  | { type: "width"; percent: number };

const initialState = (): ArtifactPanelState => ({
  open: false,
  selectedKey: null,
  selected: null,
  selectedVersionId: null,
  tab: "preview",
  sourceFile: null,
  panelPercent: 55,
  requestNonce: 0,
  registry: {},
  autoOpened: {},
  manuallyClosed: {},
});

export function artifactPanelReducer(
  state: ArtifactPanelState,
  action: Action,
): ArtifactPanelState {
  if (action.type === "reset") {
    return { ...initialState(), panelPercent: state.panelPercent };
  }
  if (action.type === "register") {
    const previous = state.registry[action.key];
    if (previous && JSON.stringify(previous) === JSON.stringify(action.block)) return state;
    const registry = { ...state.registry, [action.key]: action.block };
    const selected = state.selectedKey === action.key ? action.block : state.selected;
    const becameReady = previous?.status === "generating" && action.block.status === "ready";
    const firstPublicReady = action.autoOpenOnMount
      && !previous
      && action.block.status === "ready"
      && !Object.values(state.autoOpened).some(Boolean);
    const shouldOpen = (becameReady || firstPublicReady)
      && !state.autoOpened[action.key]
      && !state.manuallyClosed[action.key];
    if (!shouldOpen) return { ...state, registry, selected };
    return {
      ...state,
      registry,
      open: true,
      selectedKey: action.key,
      selected: action.block,
      selectedVersionId: action.block.version_id ?? null,
      tab: "preview",
      sourceFile: null,
      requestNonce: state.requestNonce + 1,
      autoOpened: { ...state.autoOpened, [action.key]: true },
    };
  }
  if (action.type === "unregister") {
    // Keep card snapshots for the workspace lifetime. Transcript cards can be
    // temporarily unmounted by reconciliation or virtualization; the explicit
    // workspace reset owns the session boundary and clears this registry.
    return state;
  }
  if (action.type === "open") {
    return {
      ...state,
      open: true,
      selectedKey: action.key,
      selected: action.block,
      selectedVersionId: action.block.version_id ?? null,
      tab: "preview",
      sourceFile: null,
      requestNonce: state.requestNonce + 1,
      manuallyClosed: { ...state.manuallyClosed, [action.key]: false },
    };
  }
  if (action.type === "close") {
    return {
      ...state,
      open: false,
      manuallyClosed: state.selectedKey
        ? { ...state.manuallyClosed, [state.selectedKey]: true }
        : state.manuallyClosed,
    };
  }
  if (action.type === "tab") return { ...state, tab: action.tab };
  if (action.type === "source") return { ...state, sourceFile: action.path };
  if (action.type === "version") {
    return {
      ...state,
      selectedVersionId: action.versionId,
      tab: "preview",
      sourceFile: null,
    };
  }
  return { ...state, panelPercent: action.percent };
}

export function artifactPanelKey(block: ArtifactBlock): string {
  return block.publication_id
    || block.public_capability
    || block.version_id
    || `${block.scope}:${block.identifier}:${block.version ?? "pending"}`;
}

interface ArtifactPanelContextValue {
  state: ArtifactPanelState;
  autoOpenOnMount: boolean;
  register: (block: ArtifactBlock) => void;
  unregister: (key: string) => void;
  open: (block: ArtifactBlock, origin?: HTMLElement | null) => void;
  close: () => void;
  setTab: (tab: ArtifactTab) => void;
  setSourceFile: (path: string | null) => void;
  setVersion: (versionId: string | null) => void;
  setPanelPercent: (percent: number) => void;
  reset: () => void;
}

const ArtifactPanelContext = React.createContext<ArtifactPanelContextValue | null>(null);

export const ArtifactPanelProvider: React.FC<{
  children: React.ReactNode;
  workspaceKey: string;
  autoOpenOnMount?: boolean;
}> = ({ children, workspaceKey, autoOpenOnMount = false }) => {
  const [state, dispatch] = React.useReducer(artifactPanelReducer, undefined, initialState);
  const originRef = React.useRef<HTMLElement | null>(null);
  const priorWorkspaceRef = React.useRef(workspaceKey);

  React.useEffect(() => {
    if (priorWorkspaceRef.current === workspaceKey) return;
    priorWorkspaceRef.current = workspaceKey;
    originRef.current = null;
    dispatch({ type: "reset" });
  }, [workspaceKey]);

  const close = React.useCallback(() => {
    dispatch({ type: "close" });
    window.setTimeout(() => originRef.current?.focus(), 0);
  }, []);

  const register = React.useCallback((block: ArtifactBlock) => dispatch({
    type: "register",
    key: artifactPanelKey(block),
    block,
    autoOpenOnMount,
  }), [autoOpenOnMount]);
  const unregister = React.useCallback((key: string) => dispatch({ type: "unregister", key }), []);
  const open = React.useCallback((block: ArtifactBlock, origin?: HTMLElement | null) => {
    originRef.current = origin ?? null;
    dispatch({ type: "open", key: artifactPanelKey(block), block });
  }, []);
  const setTab = React.useCallback((tab: ArtifactTab) => dispatch({ type: "tab", tab }), []);
  const setSourceFile = React.useCallback((path: string | null) => dispatch({ type: "source", path }), []);
  const setVersion = React.useCallback((versionId: string | null) => dispatch({ type: "version", versionId }), []);
  const setPanelPercent = React.useCallback((percent: number) => dispatch({ type: "width", percent }), []);
  const reset = React.useCallback(() => dispatch({ type: "reset" }), []);

  const value = React.useMemo<ArtifactPanelContextValue>(() => ({
    state,
    autoOpenOnMount,
    register,
    unregister,
    open,
    close,
    setTab,
    setSourceFile,
    setVersion,
    setPanelPercent,
    reset,
  }), [autoOpenOnMount, close, open, register, reset, setPanelPercent, setSourceFile, setTab, setVersion, state, unregister]);

  return <ArtifactPanelContext.Provider value={value}>{children}</ArtifactPanelContext.Provider>;
};

export function useArtifactPanel(): ArtifactPanelContextValue {
  const value = React.useContext(ArtifactPanelContext);
  if (!value) throw new Error("Poster artifacts require an ArtifactPanelProvider");
  return value;
}
