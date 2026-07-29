interface Props {
  before: unknown;
  after: unknown;
}

export const CurationDiff = ({ before, after }: Props) => (
  <details className="rounded-md border bg-muted/30 p-3 text-xs">
    <summary className="cursor-pointer font-medium">Review before / after diff</summary>
    <div className="mt-3 grid gap-3 sm:grid-cols-2">
      <div>
        <strong>Before</strong>
        <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap">
          {JSON.stringify(before, null, 2)}
        </pre>
      </div>
      <div>
        <strong>After</strong>
        <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap">
          {JSON.stringify(after, null, 2)}
        </pre>
      </div>
    </div>
  </details>
);
