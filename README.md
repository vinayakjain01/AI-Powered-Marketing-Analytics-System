# AI-Powered Marketing Analytics System

Raw Meta Ads and Shopify exports → cleaned and loaded into a Postgres star schema → **Power BI** dashboard,
a **React web app** with live dashboards, and a **Text-to-SQL AI agent** you can reach from the web app, a REST
API, or Claude Desktop (MCP).

![legacy](docs/legacy_streamlit_1.png)
*(Screenshot of the original Streamlit prototype this project grew from.)*

## What it does

* **Warehouse** (`SQL/schema.sql`, `pipeline/`): one command rebuilds everything from the CSVs.
* **Dashboard** (React): KPIs, trends and breakdowns for ads (spend, ROAS, ROI, CPC, CTR) and store sales, with
  brand / region / date filters. Every number comes from fixed, parameterised SQL.
* **Ask AI**: type a question; a Gemini agent searches the schema, writes **read-only** SQL, fixes its own errors,
  and answers with the SQL, a data table/chart and a step-by-step trace you can inspect.
* **MCP server**: the same four tools for Claude Desktop.

## Architecture

```mermaid
flowchart LR
  CSV[Raw CSVs<br/>Meta Ads, Shopify] --> CLEAN[pipeline/<br/>cleaning]
  CLEAN --> PG[(Postgres star schema<br/>campaign_data)]
  PG --> PBI[Power BI]
  PG --> TOOLS
  subgraph agent [agent/ - shared core]
    TOOLS[tools.py<br/>search_schema / get_schema /<br/>run_sql / explain_result]
    RAG[schema_rag.py<br/>+ schema_docs.yaml]
    GUARD[sql_guard + read-only txn]
    LOOP[agent.py<br/>Gemini function-calling loop]
    TOOLS --- RAG
    TOOLS --- GUARD
    LOOP --> TOOLS
  end
  LOOP --> API[FastAPI<br/>/api/*]
  PG --> API
  API --> WEB[React app<br/>Dashboard / Ask AI / Data]
  TOOLS --> MCP[MCP server] --> CD[Claude Desktop]
```

## The agent, in one minute

| Tool | What it does |
|---|---|
| `search_schema(question, top_k)` | RAG: embeds the question and returns the most relevant tables (descriptions + synonyms from `schema_docs.yaml`). Gemini embeddings (`gemini-embedding-001`) with an offline TF-IDF fallback. |
| `get_schema(tables)` | Columns, types, keys, business descriptions and up to 5 sample values per text column, so filters match exact spellings (`'brand b'`, `'usa'`). |
| `run_sql(sql)` | Runs one read-only SELECT. Errors are **returned to the model, never raised**, so it can fix and retry (max 3 SQL failures). |
| `explain_result()` | Profiles the last result (row count, min/max/mean/sum, top values) to ground the answer. |

`agent/agent.py` runs the tool-calling loop **manually** (automatic function calling off) so it can cap steps,
cap retries, and record a trace of every call (tool, args, ok, ms).

**Two safety layers.** (1) `sql_guard.py` parses the SQL with sqlglot: exactly one statement, SELECT/WITH/UNION
only, no DML/DDL/`SELECT INTO`, a blocklist of dangerous functions (`pg_sleep`, `pg_read_file`, …), and a forced
`LIMIT`. (2) `db.py` executes inside `SET TRANSACTION READ ONLY` with `statement_timeout` and always rolls back.
Either could miss something alone; together a bypass needs two independent failures. Staging tables and the Power
BI view are hidden from the agent (`hidden:` in `schema_docs.yaml`).

**Metric definitions** (always recomputed from SUMs; `fact_ads.ctr/cpm/cpc/roi` are averages of per-row ratios,
kept only for Power BI compatibility): CTR = clicks/impressions, CPC = spend/clicks, CPM = spend/impressions×1000,
ROAS = revenue/spend, ROI = (revenue − spend)/spend.

## Quick start

```bash
git clone https://github.com/vinayakjain01/AI-Powered-Marketing-Analytics-System.git
cd AI-Powered-Marketing-Analytics-System
pip install -r requirements-dev.txt
cp .env.example .env            # fill in DATABASE_URL (and GEMINI_API_KEY for the agent)

python scripts/build_warehouse.py          # CSV -> cleaned -> staging -> star schema, prints row counts

# Backend + production frontend on one port
cd frontend && npm ci && npm run build && cd ..
uvicorn api.main:app --port 8000           # open http://localhost:8000

# Or frontend with hot reload (second terminal): cd frontend && npm run dev   -> http://localhost:5173
```
Without `GEMINI_API_KEY` the dashboard and Data pages work; the Ask page shows "agent disabled".

> **Gemini free tier:** limits are low (a question uses ~5 model calls; `gemini-2.5-flash` was capped at 5 requests/minute and 20/day when tested). The agent waits out per-minute limits and fails fast with a clear message on a daily cap. Set `GEMINI_MODEL` (e.g. `gemini-3-flash-preview`) or enable billing if you hit it.

CLI: `python -m agent.agent "Top 5 campaigns by ROI"`.

## REST API

`GET /api/health` · `GET /api/tables` · `GET /api/search?q=` · `POST /api/ask {question}` →
`{answer, sql, steps, trace, columns, rows}` · dashboard: `/api/filters`, `/api/kpis`, `/api/trend`,
`/api/breakdown`, `/api/store/breakdown`, `/api/campaigns`. Interactive docs at `/docs`.

## Connect Claude Desktop (MCP)

The server needs no Gemini key; Claude does the reasoning. Edit `claude_desktop_config.json`
(Windows: `%APPDATA%\Claude\`, macOS: `~/Library/Application Support/Claude/`) and restart Claude Desktop.

**Windows**
```json
{
  "mcpServers": {
    "marketing-analytics": {
      "command": "C:\\Users\\YOU\\AppData\\Local\\Programs\\Python\\Python311\\python.exe",
      "args": ["C:\\path\\to\\AI-Powered-Marketing-Analytics-System\\mcp_entry.py"],
      "env": { "DATABASE_URL": "postgresql://user:pass@localhost:5432/campaign" }
    }
  }
}
```
**macOS**
```json
{
  "mcpServers": {
    "marketing-analytics": {
      "command": "/usr/local/bin/python3",
      "args": ["/path/to/AI-Powered-Marketing-Analytics-System/mcp_entry.py"],
      "env": { "DATABASE_URL": "postgresql://user:pass@localhost:5432/campaign" }
    }
  }
}
```
Use the Python that has `requirements.txt` installed. `mcp_entry.py` works from any directory. Add `--http` for
streamable HTTP. `python scripts/verify_mcp.py` runs a real client session over stdio (initialize → list_tools →
`run_sql` → blocked write).

## Tests

```bash
python -m pytest -q                                  # 73 tests, no Gemini key, no real database
TEST_DATABASE_URL=postgresql://.../scratch_db python -m pytest -q   # +6 Postgres tests (drops campaign_data tables!)
python scripts/eval_retrieval.py --k 3               # retrieval recall@3 on eval_questions.yaml
```
Covers the SQL guard, RAG, tools, the agent loop (scripted fake Gemini: search → schema → failed SQL → corrected
SQL → explain → answer, plus step/retry limits), MCP, the API, the cleaning rules and the Postgres warehouse.
GitHub Actions runs all of it plus the frontend build on every push.

## Data pipeline notes (what was found and fixed)

* **Mixed date formats.** The exports went through a US-locale spreadsheet: dates with day ≤ 12 were re-read as
  MM/DD, the rest stayed DD/MM. Treating everything as DD/MM spread campaign data over 12 months; with the rule in
  `pipeline/common.py` it spans 2026-01-01 → 2026-03-28, and Shopify dates agree with order timestamps ~90% of the
  time (almost all the rest are one-day UTC offsets).
* **Fact table fan-out.** The old fact load joined on columns that could be NULL or duplicated per status, giving
  19,624 rows and ₹277.5M spend against a true ₹84.1M. Now `fact_ads` = 6,234 rows and reconciles with staging
  to the rupee.
* `sales_platform` actually holds the **brand** (`brand a` / `brand b`); `brand` was added and the old name kept
  for Power BI. Shopify is now loaded (`fact_order_lines`, `dim_product`).
* Shopify caveats: ~500 rows without Order ID or date are dropped; the export has very large outlier rows, so
  averages such as AOV look high; each row is a pre-aggregated line, so use `SUM(orders)`, not `COUNT(*)`.

## Layout

```
agent/      tools, sql_guard, db, schema_rag, agent loop, MCP server     api/        FastAPI app + dashboard SQL
pipeline/   cleaning + warehouse loader      scripts/   build_warehouse, eval_retrieval, draft_schema_docs, verify_mcp
SQL/        schema.sql (build), powerbi_queries.sql     frontend/  React + Vite + TypeScript
schema_docs.yaml   business descriptions + synonyms (RAG)       eval_questions.yaml   retrieval eval set
tests/      pytest suite      Python/   exploration notebooks (call pipeline/)      Power BI/   dashboard (untouched)
```

## Deployment (SAP BTP Cloud Foundry / Docker)

See [docs/DEPLOY_BTP.md](docs/DEPLOY_BTP.md). The files are prepared but have **not** been deployed or tested on BTP.

## Limits (honest)

* Live Gemini calls have not been exercised in this repo's test runs (tests use a scripted fake client); the
  agent's behaviour with the real model is unmeasured.
* Retrieval recall is measured on a small, self-written set (19 questions) with the offline TF-IDF backend only.
* The deployed API has no authentication.

## Author

**Vinayak Jain** · Data Analyst · [LinkedIn](https://www.linkedin.com/in/vinayak-jain-69801b328)
