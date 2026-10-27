import type { ReactNode } from "react";
import { cell } from "../format";

export function Card({ title, actions, children }: { title?: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="card">
      {(title || actions) && (
        <div className="card-head">
          {title && <h2>{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export type Tone = "primary" | "teal" | "gold" | "coral" | "amber" | "lilac";

export function Kpi({ label, value, hint, tone = "primary" }: { label: string; value: string; hint?: string; tone?: Tone }) {
  return (
    <div className={`card kpi tone-${tone}`}>
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {hint && <div className="hint">{hint}</div>}
    </div>
  );
}

export function Segmented<T extends string>({ value, options, onChange, label }: {
  value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string;
}) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} aria-pressed={o.value === value} onClick={() => onChange(o.value)}>{o.label}</button>
      ))}
    </div>
  );
}

export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div style={{ display: "grid", gap: 10 }} aria-busy="true" aria-label="Loading">
      {Array.from({ length: lines }).map((_, i) => <div key={i} className="skeleton" style={{ width: `${90 - i * 12}%` }} />)}
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  return <p className="error" role="alert">Couldn't load this: {error instanceof Error ? error.message : String(error)}</p>;
}

/** Generic table for query results; numeric columns are right-aligned. */
export function DataTable({ columns, rows }: { columns: string[]; rows: (string | number | null)[][] }) {
  if (!rows.length) return <div className="empty">No rows returned.</div>;
  const numeric = columns.map((_, i) => rows.every((r) => r[i] == null || typeof r[i] === "number"));
  return (
    <div className="table-wrap">
      <table>
        <thead><tr>{columns.map((c, i) => <th key={c} className={numeric[i] ? "r" : ""}>{c}</th>)}</tr></thead>
        <tbody>
          {rows.map((r, ri) => (
            <tr key={ri}>{r.map((v, i) => <td key={i} className={numeric[i] ? "r" : ""}>{cell(v)}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
