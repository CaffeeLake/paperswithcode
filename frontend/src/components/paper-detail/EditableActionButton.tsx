import type { ReactNode } from "react";

interface EditableActionButtonProps {
  children: ReactNode;
  showEdit?: boolean;
  onEdit: () => void;
  editAriaLabel: string;
}

export function EditableActionButton({
  children,
  showEdit = false,
  onEdit,
  editAriaLabel,
}: EditableActionButtonProps) {
  if (!showEdit) {
    return children;
  }

  return (
    <span className="action-btn-composite">
      {children}
      <button
        type="button"
        className="action-btn-segment action-btn-edit"
        onClick={onEdit}
        aria-label={editAriaLabel}
      >
        edit
      </button>
    </span>
  );
}
