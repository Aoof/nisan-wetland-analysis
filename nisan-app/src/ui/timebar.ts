/** Bottom time bar drawn like a river-gauge strip: satellite passes are tick marks, "now" is the waterline, the forecast is hatched. */

export interface TimeRow { label: string; color: string; times: Date[] }
export interface TimebarOpts { el: HTMLElement; start: Date; end: Date; now: Date; onChange: (t: Date) => void }

const day = 864e5;
const ICON = {
  prev: `<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M10.5 3 5.5 8l5 5" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>`,
  next: `<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="m5.5 3 5 5-5 5" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>`,
};

export class Timebar {
  t: Date;
  private rows: TimeRow[] = [];
  private track: HTMLDivElement;
  private label: HTMLElement;
  private rel: HTMLElement;
  private gutter = 0;
  private timer: number | null = null;

  constructor(private o: TimebarOpts) {
    this.t = o.now;
    o.el.innerHTML = `
      <div class="tb-ctrl">
        <div class="tb-when"></div><div class="tb-rel"></div>
        <div class="tb-btns">
          <button data-a="prev" title="Previous satellite pass" aria-label="Previous satellite pass">${ICON.prev}</button>
          <button data-a="next" title="Next satellite pass" aria-label="Next satellite pass">${ICON.next}</button>
          <button data-a="now" class="tb-now">Now</button>
        </div>
      </div>
      <div class="tb-track" role="slider" tabindex="0" aria-label="Map time"></div>`;
    this.track = o.el.querySelector(".tb-track")!;
    this.label = o.el.querySelector(".tb-when")!;
    this.rel = o.el.querySelector(".tb-rel")!;
    o.el.querySelector(".tb-ctrl")!.addEventListener("click", (e) => {
      const a = (e.target as HTMLElement).closest("button")?.dataset.a;
      if (a === "now") this.set(this.o.now);
      if (a === "prev") this.step(-1);
      if (a === "next") this.step(1);
    });
    let drag = false;
    const at = (ev: PointerEvent) => {
      const r = this.track.getBoundingClientRect();
      const f = Math.min(1, Math.max(0, (ev.clientX - r.left - this.gutter) / (r.width - this.gutter)));
      this.set(new Date(this.o.start.getTime() + f * (this.o.end.getTime() - this.o.start.getTime())), true);
    };
    this.track.addEventListener("pointerdown", (e) => { drag = true; this.track.setPointerCapture(e.pointerId); at(e); });
    this.track.addEventListener("pointermove", (e) => drag && at(e));
    this.track.addEventListener("pointerup", () => { drag = false; this.commit(); });
    this.track.addEventListener("keydown", (e) => {
      if (e.key === "ArrowLeft") this.set(new Date(this.t.getTime() - day));
      if (e.key === "ArrowRight") this.set(new Date(this.t.getTime() + day));
    });
    new ResizeObserver(() => this.draw()).observe(this.track);
    this.draw();
  }

  setRows(rows: TimeRow[]) { this.rows = rows; this.draw(); }

  private times(): Date[] {
    return this.rows.flatMap((r) => r.times).filter((d) => d >= this.o.start && d <= this.o.end).sort((a, b) => a.getTime() - b.getTime());
  }

  step(dir: 1 | -1) {
    const p = this.times(), cur = this.t.getTime();
    const next = dir > 0 ? p.find((d) => d.getTime() > cur + 60_000) : [...p].reverse().find((d) => d.getTime() < cur - 60_000);
    if (next) this.set(next);
  }

  /** Dragging updates the readout at once; the map and panels follow 150 ms after the last movement. */
  private commit() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = window.setTimeout(() => this.o.onChange(this.t), 150);
  }

  set(t: Date, dragging = false) {
    this.t = new Date(Math.min(this.o.end.getTime(), Math.max(this.o.start.getTime(), t.getTime())));
    this.draw();
    if (!dragging) this.commit();
  }

  draw() {
    const { start, end, now } = this.o;
    const W = this.track.clientWidth || 800, H = this.track.clientHeight || 80;
    const G = (this.gutter = W > 560 ? 96 : 0);
    const x = (d: Date) => G + ((d.getTime() - start.getTime()) / (end.getTime() - start.getTime())) * (W - G);
    const top = 16, rh = Math.min(16, (H - top - 8) / Math.max(1, this.rows.length));
    const p: string[] = [];
    p.push(`<defs><pattern id="hatch" width="6" height="6" patternTransform="rotate(45)" patternUnits="userSpaceOnUse"><line x1="0" y1="0" x2="0" y2="6" stroke="var(--rule)" stroke-width="2"/></pattern></defs>`);
    p.push(`<rect x="${x(now)}" y="0" width="${Math.max(0, W - x(now))}" height="${H}" fill="url(#hatch)"/>`);
    p.push(`<text x="${x(now) + 6}" y="11" class="tb-tx">forecast</text>`);
    const d = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 1));
    for (; d <= end; d.setUTCMonth(d.getUTCMonth() + 1)) {
      p.push(`<line x1="${x(d)}" x2="${x(d)}" y1="0" y2="${H}" stroke="var(--rule)"/>`);
      p.push(`<text x="${x(d) + 4}" y="11" class="tb-tx">${d.toLocaleDateString("en-US", { month: "short", timeZone: "UTC" })}</text>`);
    }
    this.rows.forEach((r, i) => {
      const y = top + i * rh;
      if (G) p.push(`<text x="8" y="${y + rh - 4}" class="tb-row" style="fill:${r.color}">${r.label}</text>`);
      for (const t of r.times) if (t >= start && t <= end) p.push(`<rect x="${x(t) - 1}" y="${y + 2}" width="2.4" height="${rh - 4}" fill="${r.color}"/>`);
    });
    p.push(`<line x1="${x(now)}" x2="${x(now)}" y1="0" y2="${H}" stroke="var(--water)" stroke-width="2"/>`);
    const xt = x(this.t);
    p.push(`<line x1="${xt}" x2="${xt}" y1="0" y2="${H}" stroke="var(--ink)" stroke-width="2"/><rect x="${xt - 5}" y="${H - 14}" width="10" height="10" fill="var(--ink)"/>`);
    this.track.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${p.join("")}</svg>`;
    this.track.setAttribute("aria-valuetext", this.t.toISOString());
    this.label.textContent = this.t.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
    const dd = (this.t.getTime() - now.getTime()) / day;
    this.rel.textContent = Math.abs(dd) < 0.5 ? "Now" : dd > 0 ? `Forecast, +${dd.toFixed(0)} days` : `${(-dd).toFixed(0)} days ago`;
  }
}
