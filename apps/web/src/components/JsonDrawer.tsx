type JsonDrawerProps = {
  title?: string;
  value: unknown;
};

export function JsonDrawer({ title = "Raw JSON", value }: JsonDrawerProps) {
  return (
    <details className="rounded-md border border-taurus-outline bg-taurus-shell">
      <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-taurus-text">
        {title}
      </summary>
      <pre className="max-h-96 overflow-auto border-t border-taurus-outline p-4 font-mono text-xs text-slate-200">
        {JSON.stringify(value ?? null, null, 2)}
      </pre>
    </details>
  );
}
