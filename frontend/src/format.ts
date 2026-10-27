// Number formatting helpers. Amounts are INR; Indian digit grouping reads naturally to the audience.

const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

export function compactINR(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "-";
  const a = Math.abs(v);
  if (a >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`;
  if (a >= 1e5) return `₹${(v / 1e5).toFixed(2)} L`;
  if (a >= 1e3) return `₹${(v / 1e3).toFixed(1)}K`;
  return `₹${v.toFixed(0)}`;
}

export function num(v: number | null | undefined): string {
  return v == null || Number.isNaN(v) ? "-" : inr.format(v);
}

export function ratio(v: number | null | undefined, digits = 2, suffix = ""): string {
  return v == null || Number.isNaN(v) ? "-" : `${v.toFixed(digits)}${suffix}`;
}

export function pct(v: number | null | undefined, digits = 2): string {
  return v == null || Number.isNaN(v) ? "-" : `${(v * 100).toFixed(digits)}%`;
}

/** Format a raw table cell: numbers get grouping/decimals, everything else is shown as text. */
export function cell(v: string | number | null): string {
  if (v == null) return "-";
  if (typeof v === "number") return Number.isInteger(v) ? inr.format(v) : v.toLocaleString("en-IN", { maximumFractionDigits: 3 });
  return v;
}
