import { CodexPaperJobDialog } from "@/components/paper-detail/CodexPaperJobDialog";

interface CodexAddEvalsDialogProps {
  paperId: number;
  paperTitle: string;
  onComplete: () => void;
}

export function CodexAddEvalsDialog(props: CodexAddEvalsDialogProps) {
  return <CodexPaperJobDialog {...props} kind="add-evals" triggerClassName="edit-link" />;
}
