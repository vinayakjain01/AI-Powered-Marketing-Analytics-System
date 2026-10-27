import { useState } from "react";
import { Search } from "lucide-react";
import { api } from "../api";
import { useAsync } from "../useAsync";
import { Card, ErrorNote, Skeleton } from "../components/ui";

const TRY = ["total ad spend by month", "GMV by product type", "worst cost per click", "returning customers"];

export default function Schema() {
  const tables = useAsync(() => api.tables(), []);
  const health = useAsync(() => api.health(), []);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<{ table: string; score: number }[] | null>(null);
  const [err, setErr] = useState<unknown>(null);

  async function run(query: string) {
    setQ(query);
    if (query.trim().length < 2) return setHits(null);
    try { setHits((await api.search(query)).tables); setErr(null); } catch (e) { setErr(e); }
  }

  return (
    <>
      <Card title="Try the retrieval step (RAG)">
        <p className="muted" style={{ marginTop: 0 }}>
          This is the agent's first move: it embeds your question and finds the tables whose descriptions match best
          {health.data ? ` (embedding backend: ${health.data.embeddings})` : ""}.
        </p>
        <div className="filters">
          <label className="field" style={{ flex: 1, minWidth: 240 }}>Question
            <span style={{ position: "relative", display: "block" }}>
              <Search size={16} aria-hidden style={{ position: "absolute", left: 10, top: 11, color: "var(--muted)" }} />
              <input className="text-input" style={{ paddingLeft: 32, width: "100%" }} value={q} onChange={(e) => run(e.target.value)} placeholder="Type a business question…" />
            </span>
          </label>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
          {TRY.map((t) => <button key={t} className="chip" onClick={() => run(t)}>{t}</button>)}
        </div>
        {err ? <ErrorNote error={err} /> : null}
        {hits && (
          <ol style={{ margin: "14px 0 0", paddingLeft: 20 }}>
            {hits.map((h) => <li key={h.table}><strong>{h.table}</strong> <span className="muted num">score {h.score.toFixed(3)}</span></li>)}
          </ol>
        )}
      </Card>

      <h3 className="section-title">Tables the agent can see</h3>
      {tables.error ? <ErrorNote error={tables.error} /> : !tables.data ? <Skeleton lines={5} /> : (
        <div className="grid" style={{ gap: 16 }}>
          {tables.data.tables.map((t) => (
            <Card key={t.name} title={t.name}>
              <p style={{ marginTop: 0 }}>{t.description}</p>
              {t.synonyms.length > 0 && (
                <p style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                  <span className="muted" style={{ fontSize: 12 }}>Also called</span>
                  {t.synonyms.slice(0, 10).map((s) => <span key={s} className="tag">{s}</span>)}
                </p>
              )}
              <details>
                <summary className="muted" style={{ cursor: "pointer", fontSize: 13 }}>{t.columns.length} columns</summary>
                <div className="table-wrap" style={{ marginTop: 8 }}>
                  <table>
                    <thead><tr><th>Column</th><th>Type</th><th>Meaning</th></tr></thead>
                    <tbody>
                      {t.columns.map((c) => (
                        <tr key={c.name}>
                          <td><strong>{c.name}</strong>{t.primary_key.includes(c.name) ? " 🔑" : ""}</td>
                          <td className="muted">{c.type}</td>
                          <td style={{ whiteSpace: "normal", minWidth: 280 }}>{c.description || <span className="muted">-</span>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
