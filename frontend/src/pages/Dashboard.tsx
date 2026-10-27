import { useState } from "react";
import {
  Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api, type Filters, type Row } from "../api";
import { compactINR, num, pct, ratio } from "../format";
import { useAsync } from "../useAsync";
import { Card, ErrorNote, Kpi, Segmented, Skeleton } from "../components/ui";

const AXIS = { stroke: "var(--text-muted)", fontSize: 12 } as const;
const TOOLTIP = {
  contentStyle: { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, color: "var(--text)" },
  labelStyle: { color: "var(--text-secondary)" },
} as const;

type Grain = "day" | "week" | "month";
const ADS_BY = [
  { value: "region", label: "Region" }, { value: "brand", label: "Brand" }, { value: "country", label: "Country" },
  { value: "funnel_stage", label: "Funnel stage" }, { value: "status", label: "Status" },
  { value: "weekday", label: "Weekday" },
];
const STORE_BY = [
  { value: "channel", label: "Channel" }, { value: "product_type", label: "Product type" },
  { value: "country", label: "Country" }, { value: "customer_type", label: "Customer" },
];
const RANK = [
  { value: "roas", label: "ROAS" }, { value: "spend", label: "Spend" }, { value: "revenue", label: "Revenue" },
  { value: "cpc", label: "CPC" }, { value: "purchases", label: "Purchases" },
];

const n = (v: unknown) => (typeof v === "number" ? v : 0);

export default function Dashboard() {
  const meta = useAsync(() => api.filters(), []);
  const [brand, setBrand] = useState("");
  const [region, setRegion] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const f: Filters = { brand, region, start, end };
  const key = [brand, region, start, end];

  const [grain, setGrain] = useState<Grain>("week");
  const [adsBy, setAdsBy] = useState("region");
  const [storeBy, setStoreBy] = useState("channel");
  const [rank, setRank] = useState("roas");
  const [order, setOrder] = useState("desc");
  const [minSpend, setMinSpend] = useState(10000);

  const kpis = useAsync(() => api.kpis(f), key);
  const trend = useAsync(() => api.trend(f, grain), [...key, grain]);
  const ads = useAsync(() => api.breakdown(f, adsBy), [...key, adsBy]);
  const store = useAsync(() => api.storeBreakdown(f, storeBy), [...key, storeBy]);
  const camps = useAsync(() => api.campaigns(f, rank, order, minSpend), [...key, rank, order, minSpend]);

  const a = kpis.data?.ads;
  const s = kpis.data?.store;
  const trendRows = (trend.data?.ads ?? []).map((r) => ({ period: r.period, spend: n(r.spend), revenue: n(r.revenue), roas: r.roas }));
  const storeTrend = new Map((trend.data?.store ?? []).map((r) => [r.period, n(r.net_sales)]));
  const merged = trendRows.map((r) => ({ ...r, net_sales: storeTrend.get(r.period) ?? 0 }));

  return (
    <>
      <Card>
        <div className="filters">
          <label className="field">Brand
            <select value={brand} onChange={(e) => setBrand(e.target.value)}>
              <option value="">All brands</option>
              {meta.data?.brands.map((b) => <option key={b}>{b}</option>)}
            </select>
          </label>
          <label className="field">Region
            <select value={region} onChange={(e) => setRegion(e.target.value)}>
              <option value="">All regions</option>
              {meta.data?.regions.map((r) => <option key={r}>{r}</option>)}
            </select>
          </label>
          <label className="field">From
            <input type="date" value={start} min={meta.data?.date_min} max={meta.data?.date_max} onChange={(e) => setStart(e.target.value)} />
          </label>
          <label className="field">To
            <input type="date" value={end} min={meta.data?.date_min} max={meta.data?.date_max} onChange={(e) => setEnd(e.target.value)} />
          </label>
          {(brand || region || start || end) && (
            <button className="btn" onClick={() => { setBrand(""); setRegion(""); setStart(""); setEnd(""); }}>Reset</button>
          )}
          <span className="muted" style={{ marginLeft: "auto", fontSize: 13 }}>
            Data: {meta.data ? `${meta.data.date_min} to ${meta.data.date_max}` : "…"}
          </span>
        </div>
      </Card>

      <h3 className="section-title">Ad performance (Meta Ads)</h3>
      {kpis.error ? <ErrorNote error={kpis.error} /> : (
        <div className="grid kpis">
          <Kpi tone="primary" label="Ad spend" value={a ? compactINR(a.spend) : "…"} />
          <Kpi tone="teal" label="Ad-attributed revenue" value={a ? compactINR(a.revenue) : "…"} />
          <Kpi tone="teal" label="ROAS" value={a ? ratio(a.roas, 2, "x") : "…"} hint="revenue ÷ spend" />
          <Kpi tone="amber" label="ROI" value={a ? pct(a.roi, 0) : "…"} hint="(revenue − spend) ÷ spend" />
          <Kpi tone="coral" label="CPC" value={a ? `₹${ratio(a.cpc)}` : "…"} hint="spend ÷ clicks" />
          <Kpi tone="gold" label="CTR" value={a ? pct(a.ctr) : "…"} hint="clicks ÷ impressions" />
          <Kpi tone="lilac" label="Purchases" value={a ? num(a.purchases) : "…"} />
        </div>
      )}

      <h3 className="section-title">Store sales (Shopify)</h3>
      <div className="grid kpis">
        <Kpi tone="primary" label="Net sales" value={s ? compactINR(s.net_sales) : "…"} />
        <Kpi tone="teal" label="Orders" value={s ? num(s.orders) : "…"} />
        <Kpi tone="gold" label="Avg order value" value={s ? compactINR(s.aov) : "…"} hint="net sales ÷ orders" />
        <Kpi tone="amber" label="Discounts" value={s ? compactINR(s.discounts) : "…"} />
        <Kpi tone="coral" label="Returns" value={s ? compactINR(s.returns) : "…"} />
      </div>
      <p className="muted" style={{ fontSize: 12, margin: "8px 0 0" }}>
        Store figures include a few very large rows in the source export, so averages such as AOV can look high.
      </p>

      <h3 className="section-title">Trend</h3>
      <Card
        title="Ad spend vs ad revenue vs store net sales"
        actions={<Segmented label="Time grain" value={grain} onChange={setGrain}
          options={[{ value: "day", label: "Day" }, { value: "week", label: "Week" }, { value: "month", label: "Month" }]} />}
      >
        {trend.error ? <ErrorNote error={trend.error} /> : trend.loading && !trend.data ? <Skeleton lines={5} /> : (
          <div role="img" aria-label="Line chart of spend, revenue and net sales over time" style={{ height: 320 }}>
            <ResponsiveContainer>
              <ComposedChart data={merged} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="period" {...AXIS} />
                <YAxis {...AXIS} tickFormatter={(v) => compactINR(v)} width={70} />
                <Tooltip {...TOOLTIP} formatter={(v) => compactINR(Number(v))} />
                <Legend />
                <Line isAnimationActive={false} type="monotone" dataKey="spend" name="Ad spend" stroke="var(--c2)" strokeWidth={2.5} dot={false} />
                <Line isAnimationActive={false} type="monotone" dataKey="revenue" name="Ad revenue" stroke="var(--c1)" strokeWidth={2.5} dot={false} />
                <Line isAnimationActive={false} type="monotone" dataKey="net_sales" name="Store net sales" stroke="var(--c3)" strokeWidth={2.5} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      <div className="grid two" style={{ marginTop: 16 }}>
        <Card title="Ads breakdown" actions={<Segmented label="Ads breakdown dimension" value={adsBy} onChange={setAdsBy} options={ADS_BY} />}>
          <BreakdownChart state={ads} cols={[{ k: "spend", name: "Spend", color: "var(--c2)" }, { k: "revenue", name: "Revenue", color: "var(--c1)" }]} />
          <MetricTable rows={ads.data?.rows ?? []} cols={[
            { k: "spend", h: "Spend", f: compactINR }, { k: "roas", h: "ROAS", f: (v) => ratio(v, 2, "x") },
            { k: "cpc", h: "CPC", f: (v) => `₹${ratio(v)}` }, { k: "ctr", h: "CTR", f: (v) => pct(v) }]} />
        </Card>
        <Card title="Store breakdown" actions={<Segmented label="Store breakdown dimension" value={storeBy} onChange={setStoreBy} options={STORE_BY} />}>
          <BreakdownChart state={store} cols={[{ k: "net_sales", name: "Net sales", color: "var(--c3)" }, { k: "discounts", name: "Discounts", color: "var(--c4)" }]} />
          <MetricTable rows={store.data?.rows ?? []} cols={[
            { k: "net_sales", h: "Net sales", f: compactINR }, { k: "orders", h: "Orders", f: (v) => num(v) },
            { k: "aov", h: "AOV", f: (v) => compactINR(v) }]} />
        </Card>
      </div>

      <h3 className="section-title">Campaigns</h3>
      <Card
        title="Campaign ranking"
        actions={
          <div className="filters">
            <label className="field">Rank by
              <select value={rank} onChange={(e) => setRank(e.target.value)}>{RANK.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}</select>
            </label>
            <label className="field">Order
              <select value={order} onChange={(e) => setOrder(e.target.value)}>
                <option value="desc">Highest first</option><option value="asc">Lowest first</option>
              </select>
            </label>
            <label className="field">Min spend (₹)
              <input type="number" min={0} step={1000} value={minSpend} onChange={(e) => setMinSpend(Number(e.target.value))} style={{ width: 110 }} />
            </label>
          </div>
        }
      >
        {camps.error ? <ErrorNote error={camps.error} /> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Campaign</th><th className="r">Spend</th><th className="r">Revenue</th><th className="r">ROAS</th><th className="r">CPC</th><th className="r">CTR</th><th className="r">Purchases</th></tr></thead>
              <tbody>
                {(camps.data?.rows ?? []).map((r) => (
                  <tr key={String(r.label)}>
                    <td style={{ maxWidth: 420, overflow: "hidden", textOverflow: "ellipsis" }} title={String(r.label)}>{r.label}</td>
                    <td className="r">{compactINR(n(r.spend))}</td><td className="r">{compactINR(n(r.revenue))}</td>
                    <td className="r">{ratio(r.roas as number, 2, "x")}</td><td className="r">₹{ratio(r.cpc as number)}</td>
                    <td className="r">{pct(r.ctr as number)}</td><td className="r">{num(n(r.purchases))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {camps.data && camps.data.rows.length === 0 && <div className="empty">No campaigns match these filters.</div>}
          </div>
        )}
      </Card>
    </>
  );
}

function BreakdownChart({ state, cols }: {
  state: { data: { rows: Row[] } | null; error: unknown; loading: boolean };
  cols: { k: string; name: string; color: string }[];
}) {
  if (state.error) return <ErrorNote error={state.error} />;
  if (!state.data) return <Skeleton lines={4} />;
  return (
    <div role="img" aria-label="Bar chart breakdown" style={{ height: 240, marginBottom: 12 }}>
      <ResponsiveContainer>
        <BarChart data={state.data.rows} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis dataKey="label" {...AXIS} interval={0} tick={{ fontSize: 11, fill: "var(--text-muted)" }} />
          <YAxis {...AXIS} tickFormatter={(v) => compactINR(v)} width={70} />
          <Tooltip {...TOOLTIP} formatter={(v) => compactINR(Number(v))} cursor={{ fill: "var(--primary-soft)" }} />
          <Legend />
          {cols.map((c) => <Bar isAnimationActive={false} key={c.k} dataKey={c.k} name={c.name} fill={c.color} radius={[4, 4, 0, 0]} />)}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function MetricTable({ rows, cols }: { rows: Row[]; cols: { k: string; h: string; f: (v: number | null) => string }[] }) {
  return (
    <div className="table-wrap" style={{ maxHeight: 240 }}>
      <table>
        <thead><tr><th>Group</th>{cols.map((c) => <th key={c.k} className="r">{c.h}</th>)}</tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={String(r.label)}><td>{r.label}</td>{cols.map((c) => <td key={c.k} className="r">{c.f(r[c.k] as number | null)}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
