/** Tiny SVG charts: lines (observed solid, forecast dashed) and bars, with a "now" marker. */

export interface ChartSeries {
  points: { t: Date; v: number | null }[];
  color: string;
  label: string;
  dashedAfter?: Date;
  type?: "line" | "bar" | "band";
  /** for band: upper values aligned with points */
  upper?: (number | null)[];
  width?: number;
}

export interface ChartOpts {
  width?: number;
  height?: number;
  unit?: string;
  now?: Date;
  yMin?: number;
  yMax?: number;
  hlines?: { v: number; color: string; label: string }[];
}

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);

export function chart(series: ChartSeries[], o: ChartOpts = {}): string {
  const W = o.width ?? 330, H = o.height ?? 120, L = 34, R = 6, T = 8, B = 18;
  const all = series.flatMap((s) => s.points.filter((p) => p.v != null));
  if (!all.length) return `<div class="dim">No data for this chart.</div>`;
  const t0 = Math.min(...all.map((p) => p.t.getTime())), t1 = Math.max(...all.map((p) => p.t.getTime()));
  const vs = [...all.map((p) => p.v!), ...series.flatMap((s) => (s.upper ?? []).filter((x): x is number => x != null)), ...(o.hlines ?? []).map((h) => h.v)];
  const y0 = o.yMin ?? Math.min(0, ...vs), y1 = o.yMax ?? (Math.max(...vs) * 1.08 || 1);
  const x = (t: Date) => L + ((t.getTime() - t0) / Math.max(1, t1 - t0)) * (W - L - R);
  const y = (v: number) => T + (1 - (v - y0) / Math.max(1e-9, y1 - y0)) * (H - T - B);
  const parts: string[] = [];
  // grid + y labels
  for (let i = 0; i <= 3; i++) {
    const v = y0 + ((y1 - y0) * i) / 3, yy = y(v);
    parts.push(`<line class="grid" x1="${L}" x2="${W - R}" y1="${yy}" y2="${yy}"/>`);
    parts.push(`<text x="${L - 4}" y="${yy + 3}" text-anchor="end">${fmt(v)}</text>`);
  }
  // x labels: ~4 dates
  for (let i = 0; i <= 3; i++) {
    const t = new Date(t0 + ((t1 - t0) * i) / 3);
    parts.push(`<text x="${x(t)}" y="${H - 4}" text-anchor="${i === 0 ? "start" : i === 3 ? "end" : "middle"}">${t.toLocaleDateString("en-US", { month: "short", day: "numeric" })}</text>`);
  }
  if (o.now && o.now.getTime() > t0 && o.now.getTime() < t1) {
    const xn = x(o.now);
    parts.push(`<rect x="${xn}" y="${T}" width="${W - R - xn}" height="${H - T - B}" fill="var(--rule)" opacity=".5"/>`);
    parts.push(`<line x1="${xn}" x2="${xn}" y1="${T}" y2="${H - B}" stroke="var(--water)" stroke-width="1.5"/>`);
    parts.push(`<text x="${xn + 3}" y="${T + 9}" style="fill:var(--water)">now</text>`);
  }
  for (const h of o.hlines ?? []) {
    parts.push(`<line x1="${L}" x2="${W - R}" y1="${y(h.v)}" y2="${y(h.v)}" stroke="${h.color}" stroke-dasharray="2 3"/>`);
    parts.push(`<text x="${W - R - 2}" y="${y(h.v) - 3}" text-anchor="end" style="fill:${h.color}">${esc(h.label)}</text>`);
  }
  for (const s of series) {
    const pts = s.points.filter((p) => p.v != null) as { t: Date; v: number }[];
    if (s.type === "bar") {
      const bw = Math.max(2, ((W - L - R) / Math.max(1, pts.length)) * 0.7);
      for (const p of pts) {
        const fut = s.dashedAfter && p.t > s.dashedAfter;
        parts.push(`<rect x="${x(p.t) - bw / 2}" y="${y(p.v)}" width="${bw}" height="${Math.max(0, y(y0) - y(p.v))}" fill="${s.color}" opacity="${fut ? 0.45 : 0.9}"><title>${p.t.toDateString()}: ${fmt(p.v)}${o.unit ?? ""}</title></rect>`);
      }
      continue;
    }
    if (s.type === "band" && s.upper) {
      const up = s.points.map((p, i) => ({ t: p.t, lo: p.v, hi: s.upper![i] })).filter((p) => p.lo != null && p.hi != null) as { t: Date; lo: number; hi: number }[];
      if (up.length > 1) {
        const d = up.map((p, i) => `${i ? "L" : "M"}${x(p.t)},${y(p.hi)}`).join("") + [...up].reverse().map((p) => `L${x(p.t)},${y(p.lo)}`).join("") + "Z";
        parts.push(`<path d="${d}" fill="${s.color}" opacity=".18"/>`);
      }
      continue;
    }
    const split = s.dashedAfter;
    const solid = split ? pts.filter((p) => p.t <= split) : pts;
    const dashed = split ? pts.filter((p, i) => p.t >= split || (pts[i + 1] && pts[i + 1].t > split)) : [];
    const path = (a: typeof pts) => a.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join("");
    if (solid.length > 1) parts.push(`<path d="${path(solid)}" fill="none" stroke="${s.color}" stroke-width="${s.width ?? 1.8}"/>`);
    if (dashed.length > 1) parts.push(`<path d="${path(dashed)}" fill="none" stroke="${s.color}" stroke-width="${s.width ?? 1.8}" stroke-dasharray="4 3"/>`);
    if (pts.length === 1 || (s.width ?? 0) === 0) for (const p of pts) parts.push(`<circle cx="${x(p.t)}" cy="${y(p.v)}" r="2.5" fill="${s.color}"/>`);
  }
  const legend = series.map((s) => `<span><i style="background:${s.color}"></i>${esc(s.label)}</span>`).join("");
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(series.map((s) => s.label).join(", "))}">${parts.join("")}</svg><div class="legend-inline">${legend}</div>`;
}

export function fmt(v: number): string {
  const a = Math.abs(v);
  if (a >= 1000) return `${(v / 1000).toFixed(a >= 10000 ? 0 : 1)}k`;
  if (a >= 100) return v.toFixed(0);
  if (a >= 10) return v.toFixed(0);
  return v.toFixed(a < 1 && a > 0 ? 2 : 1);
}
