import { useEffect, useRef, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Check, Copy, Send } from "lucide-react";
import { api, ApiError, type AskResponse } from "../api";
import { useAsync } from "../useAsync";
import { Card, DataTable, Segmented, Skeleton } from "../components/ui";

const EXAMPLES = [
  "Which campaign had the worst CPC in March?",
  "Top 5 campaigns by ROI with at least 50,000 spend",
  "Compare brand a and brand b performance",
  "Summarise India region performance",
  "Which product type has the highest net sales?",
  "Compare Shopify net sales with ad revenue by month",
];

interface Turn { id: number; question: string; result?: AskResponse; error?: string }

export default function Ask() {
  const health = useAsync(() => api.health(), []);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const disabled = health.data ? !health.data.agent_enabled : false;

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [turns, busy]);

  async function submit(question: string) {
    const q = question.trim();
    if (q.length < 3 || busy) return;
    const id = Date.now();
    setTurns((t) => [...t, { id, question: q }]);
    setInput("");
    setBusy(true);
    try {
      const result = await api.ask(q);
      setTurns((t) => t.map((x) => (x.id === id ? { ...x, result } : x)));
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Could not reach the server.";
      setTurns((t) => t.map((x) => (x.id === id ? { ...x, error: msg } : x)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ask">
      {disabled && (
        <div className="banner" role="status">
          The AI agent is switched off on this server (no <code>GEMINI_API_KEY</code>). The dashboard and schema pages still work.
        </div>
      )}

      {turns.length === 0 && (
        <div className="hero" style={{ textAlign: "center", padding: "36px 0 24px" }}>
          <h1>Ask your marketing data anything</h1>
          <p className="muted" style={{ maxWidth: 560, margin: "10px auto 20px" }}>
            An AI agent finds the right tables, writes read-only SQL, fixes its own mistakes, and explains the result.
            Every step is shown so you can check it.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center" }}>
            {EXAMPLES.map((e) => <button key={e} className="chip" disabled={disabled || busy} onClick={() => submit(e)}>{e}</button>)}
          </div>
        </div>
      )}

      <div className="thread" aria-live="polite">
        {turns.map((t) => (
          <div key={t.id} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div className="bubble-q">{t.question}</div>
            {t.error ? <Card><p className="error" role="alert">{t.error}</p></Card>
              : t.result ? <AnswerCard r={t.result} />
              : <Card><p className="muted" style={{ marginTop: 0 }}>Agent is working: searching schema, writing SQL…</p><Skeleton lines={3} /></Card>}
          </div>
        ))}
        <div ref={endRef} />
      </div>

      <div className="composer">
        <form onSubmit={(e) => { e.preventDefault(); submit(input); }}>
          <input className="text-input" value={input} onChange={(e) => setInput(e.target.value)} maxLength={1000}
            placeholder={disabled ? "Agent unavailable" : "e.g. Which region has the best ROAS?"} aria-label="Your question" disabled={disabled} />
          <button className="btn primary" type="submit" disabled={disabled || busy || input.trim().length < 3}>
            <Send size={16} aria-hidden /> Ask
          </button>
        </form>
      </div>
    </div>
  );
}

function AnswerCard({ r }: { r: AskResponse }) {
  const [view, setView] = useState<"table" | "chart">("table");
  const [copied, setCopied] = useState(false);
  const chart = chartable(r);
  // The model repeats the SQL in a fenced block at the end of its answer; show it once, in the SQL panel.
  const text = r.answer.replace(/```sql[\s\S]*?```/gi, "").trim();

  async function copy() {
    if (!r.sql) return;
    try { await navigator.clipboard.writeText(r.sql); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard blocked */ }
  }

  return (
    <Card>
      <div className="answer">{text || "(no answer text)"}</div>
      {r.stopped_reason !== "answered" && (
        <p className="muted" style={{ fontSize: 13 }}>Stopped early: {r.stopped_reason === "max_steps" ? "step limit reached" : "SQL kept failing"}.</p>
      )}

      {r.sql && (
        <>
          <div className="card-head" style={{ margin: "18px 0 8px" }}>
            <h2>SQL</h2>
            <button className="btn" onClick={copy}>{copied ? <Check size={14} aria-hidden /> : <Copy size={14} aria-hidden />}{copied ? "Copied" : "Copy"}</button>
          </div>
          <pre className="sql">{r.sql}</pre>
        </>
      )}

      {r.columns.length > 0 && (
        <>
          <div className="card-head" style={{ margin: "18px 0 8px" }}>
            <h2>Data <span className="muted num" style={{ fontWeight: 400 }}>({r.rows.length} rows{r.truncated ? ", truncated" : ""})</span></h2>
            {chart && <Segmented label="View" value={view} onChange={setView} options={[{ value: "table", label: "Table" }, { value: "chart", label: "Chart" }]} />}
          </div>
          {view === "chart" && chart ? (
            <div role="img" aria-label={`Bar chart of ${chart.valueKey} by ${chart.labelKey}`} style={{ height: 280 }}>
              <ResponsiveContainer>
                <BarChart data={chart.data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="label" stroke="var(--text-muted)" fontSize={11} interval={0} />
                  <YAxis stroke="var(--text-muted)" fontSize={12} width={70} />
                  <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10 }} cursor={{ fill: "var(--primary-soft)" }} />
                  <Bar isAnimationActive={false} dataKey="value" name={chart.valueKey} fill="var(--c1)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : <DataTable columns={r.columns} rows={r.rows} />}
        </>
      )}

      <details className="steps" style={{ marginTop: 16 }}>
        <summary>Agent steps ({r.trace.length} tool calls, {r.steps} model turns)</summary>
        {r.trace.map((s, i) => (
          <div className="step" key={i}>
            <span className={`dot ${s.ok ? "" : "err"}`} title={s.ok ? "ok" : "failed"} />
            <div>
              <strong>{s.tool}</strong> <span className="muted">→ {s.summary}</span>
              <div><code>{JSON.stringify(s.args)}</code></div>
            </div>
            <span className="muted num">{s.ms} ms</span>
          </div>
        ))}
      </details>
    </Card>
  );
}

/** A result is chartable when it has one text column (labels), a numeric column, and 2-30 rows. */
function chartable(r: AskResponse) {
  if (r.rows.length < 2 || r.rows.length > 30) return null;
  const isNum = (i: number) => r.rows.every((row) => row[i] == null || typeof row[i] === "number");
  const labelIdx = r.columns.findIndex((_, i) => !isNum(i));
  const valueIdx = r.columns.findIndex((_, i) => isNum(i) && i !== labelIdx);
  if (labelIdx < 0 || valueIdx < 0) return null;
  return {
    labelKey: r.columns[labelIdx], valueKey: r.columns[valueIdx],
    data: r.rows.map((row) => ({ label: String(row[labelIdx]).slice(0, 28), value: Number(row[valueIdx] ?? 0) })),
  };
}
