import { CodexPaperJobDialog } from "@/components/paper-detail/CodexPaperJobDialog";

interface CodexEnrichPaperDialogProps {
  paperId: number;
  paperTitle: string;
  onComplete: () => void;
}

export function CodexEnrichPaperDialog(props: CodexEnrichPaperDialogProps) {
  return <CodexPaperJobDialog {...props} kind="enrich-paper" triggerClassName="action-btn" />;
}
