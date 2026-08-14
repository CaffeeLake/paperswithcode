import type { PaperSectionId } from "@/hooks/usePaperDetailPageModel";

export function PaperSectionRule({
  accent,
  id,
  label,
}: {
  accent?: React.ReactNode;
  id: PaperSectionId;
  label: string;
}) {
  return (
    <div className="section-rule paper-section-anchor" id={id}>
      <span>
        <a href={`#${id}`} className="section-anchor-link">
          {label}
        </a>
      </span>
      {accent}
    </div>
  );
}
