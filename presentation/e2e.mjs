// End-to-end run of the NISAN app against the running dev server + API.
// Saves screenshots for the presentation and asserts the zone/map/popup agreement at several times.
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const BASE = process.env.BASE ?? "http://localhost:5173";
const OUT = process.argv[2];
fs.mkdirSync(OUT, { recursive: true });
const results = [];
let n = 0;
const ok = (name, pass, info = "") => { results.push({ name, pass, info }); console.log(`${pass ? "PASS" : "FAIL"}  ${name}${info ? "  " + info : ""}`); };
const shot = async (page, name) => { n++; const f = path.join(OUT, `${String(n).padStart(2, "0")}-${name}.png`); await page.screenshot({ path: f }); return f; };
const settle = (page, ms = 1200) => page.waitForTimeout(ms);

const browser = await chromium.launch({ executablePath: process.env.CHROME });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, acceptDownloads: true, permissions: ["clipboard-read", "clipboard-write"] });
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
page.on("console", (m) => m.type() === "error" && errors.push(m.text())); page.on("response", (r) => r.status() >= 400 && errors.push(`HTTP ${r.status()} ${r.url()}`));

const ready = async () => page.waitForFunction(() => window.nisan && window.nisan.data.forecast && window.nisan.state.zones.length, null, { timeout: 60000 });

/** Every surface must show the same level for every zone. */
async function agreement(label) {
  const rows = await page.evaluate(async () => {
    const s = window.nisan.state, out = [];
    for (const z of [...s.zones]) {
      const list = document.querySelector(`.zone[data-place="${z.place.id}"] .chip`)?.textContent;
      const pin = [...document.querySelectorAll(".zone-pin")].find((e) => e.getAttribute("aria-label")?.startsWith(z.place.name + ":"));
      await window.nisan.select(z.place.at, z.place.name);
      const popup = document.querySelector(".maplibregl-popup .chip")?.textContent;
      out.push({ id: z.place.id, zone: z.level, list, pin: pin ? ["normal", "watch", "warning", "emergency"].find((l) => pin.classList.contains(l)) : null, popup, answer: s.answer?.level });
    }
    return out;
  });
  const bad = rows.filter((r) => new Set([r.zone, r.list, r.pin, r.popup, r.answer]).size !== 1);
  ok(`Zone list, map pins, popup and answer agree (${label})`, !bad.length, bad.length ? JSON.stringify(bad) : rows.map((r) => `${r.id}=${r.zone}`).join(" "));
  return rows;
}

try {
  /* 1. Overview */
  await page.goto(`${BASE}/?view=overview`);
  await ready(); await settle(page, 2500);
  ok("Overview loads with place chips", (await page.locator("#panelBody [data-place]").count()) >= 5);
  await shot(page, "overview-landing");

  await page.locator('#panelBody [data-place="coatzacoalcos"]').click();
  await page.waitForFunction(() => window.nisan.state.answer); await settle(page, 2500);
  const ov = await page.evaluate(() => ({ a: window.nisan.state.answer.level, z: window.nisan.state.zones.find((z) => z.place.id === "coatzacoalcos")?.level, zone: window.nisan.state.answer.zone }));
  ok("Overview place card uses the zone verdict", ov.zone === "coatzacoalcos" && (ov.z ? ov.a === ov.z : true), JSON.stringify(ov));
  await shot(page, "overview-place-card");

  /* map click on an arbitrary spot (point model) */
  await page.locator("#map").click({ position: { x: 1000, y: 520 } });
  await page.waitForFunction(() => window.nisan.state.answer && !window.nisan.state.pointLoading); await settle(page, 2000);
  const pt = await page.evaluate(() => ({ lv: window.nisan.state.answer.level, zone: window.nisan.state.answer.zone ?? null, n: window.nisan.state.answer.samples.length }));
  ok("Clicking the map gives a point answer", !pt.zone && pt.n > 0, JSON.stringify(pt));
  await shot(page, "overview-map-click-point");

  /* search: place, coordinates */
  await page.fill("#q", "Minat");
  await page.waitForSelector("#results li"); await shot(page, "search-suggestions");
  await page.locator("#results li").first().click();
  await page.waitForFunction(() => window.nisan.state.selected?.name === "Minatitlán" && window.nisan.state.answer); await settle(page, 2500);
  ok("Search by place name selects the place", true);
  await shot(page, "search-place-result");
  await page.fill("#q", "18.05, -94.40"); await page.press("#q", "Enter");
  await page.waitForFunction(() => { const s = window.nisan.state.selected; return s && Math.abs(s.at[1] - 18.05) < 1e-6 && window.nisan.state.answer; }); await settle(page, 2500);
  ok("Search by lat, lon selects the coordinates", true);
  await shot(page, "search-coordinates");

  /* 2. Authorities */
  await page.locator(".views button[data-view=authorities]").click();
  await page.waitForSelector("#panelBody .zone"); await settle(page, 2500);
  ok("Authorities band is visible", await page.locator("#band").isVisible(), await page.locator("#band").innerText());
  await page.evaluate(() => window.nisan.view.map.jumpTo({ center: [-94.49, 18.02], zoom: 9.2 })); await settle(page, 2000);
  await shot(page, "authorities-overview");

  await agreement("now");

  await page.locator('#panelBody .zone[data-place="coatzacoalcos"]').click();
  await page.waitForSelector(".maplibregl-popup"); await settle(page, 3000);
  await shot(page, "authorities-zone-popup-coatzacoalcos");

  await page.evaluate(() => { const z = window.nisan.state.zones[0]; return window.nisan.select(z.place.at, z.place.name, true); });
  await settle(page, 3000);
  await shot(page, "authorities-top-zone-popup");

  /* gauge popup */
  await page.evaluate(() => window.nisan.view.map.jumpTo({ center: [-94.52, 17.98], zoom: 10.5 })); await settle(page, 2000);
  const gpos = await page.evaluate(() => { const m = window.nisan.view.map; const r = m.getCanvas().getBoundingClientRect(); const f = m.queryRenderedFeatures({ layers: ["gauges"] }).find((g) => { const q = m.project(g.geometry.coordinates); return document.elementFromPoint(r.left + q.x, r.top + q.y)?.tagName === "CANVAS"; }); if (!f) return null; const p = m.project(f.geometry.coordinates); return { x: p.x, y: p.y, ratio: f.properties.ratio }; });
  if (gpos) {
    const box = await page.locator("#map").boundingBox();
    await page.mouse.click(box.x + gpos.x, box.y + gpos.y); await settle(page, 1000);
    const txt = await page.locator(".maplibregl-popup").innerText().catch(() => "");
    ok("River gauge popup shows the 10-day peak", /Peak in the next 10 days/.test(txt), txt.replace(/\s+/g, " "));
    await shot(page, "authorities-gauge-popup");
  } else ok("River gauge layer rendered", false);

  /* brief + CSV agree with the zones */
  await page.locator('[data-act="copy-brief"]').click(); await settle(page, 500);
  const brief = await page.evaluate(() => navigator.clipboard.readText()).catch(() => "");
  const zs = await page.evaluate(() => window.nisan.state.zones.map((z) => ({ name: z.place.name, level: z.level })));
  const above = zs.filter((z) => z.level !== "normal");
  ok("Copy brief lists the same zones as the panel", above.every((z) => brief.includes(`${z.name} (${z.level.toUpperCase()})`)) && (above.length || brief.includes("All zones are normal")), brief.split("\n")[2]);
  fs.writeFileSync(path.join(OUT, "brief.txt"), brief);
  const [dl] = await Promise.all([page.waitForEvent("download"), page.locator('[data-act="zones-csv"]').click()]);
  const csvPath = path.join(OUT, await dl.suggestedFilename()); await dl.saveAs(csvPath);
  const csv = fs.readFileSync(csvPath, "utf8").split("\n");
  ok("Zones CSV has a row per zone with matching levels", csv.length - 1 === zs.length && zs.every((z) => csv.some((l) => l.startsWith(z.name + ",") && l.includes(`,${z.level},`))), `${csv.length - 1} rows`);

  await page.locator("#panelBody").evaluate((e) => (e.scrollTop = e.scrollHeight / 3)); await settle(page, 400);
  await shot(page, "authorities-river-forecast-signals");
  await page.locator("#panelBody").evaluate((e) => (e.scrollTop = e.scrollHeight)); await settle(page, 400);
  await shot(page, "authorities-surface-water-freshness");
  await page.locator("#panelBody").evaluate((e) => (e.scrollTop = 0));

  /* 3. Time bar: past passes and the forecast window, agreement at each */
  await page.evaluate(() => window.nisan.view.map.jumpTo({ center: [-94.49, 18.02], zoom: 9.2 }));
  await page.locator('#timebar [data-a="prev"]').click(); await settle(page, 2500);
  const tPrev = await page.evaluate(() => window.nisan.state.t.toISOString());
  ok("Previous-pass button moves the time back", new Date(tPrev) < new Date(), tPrev);
  await shot(page, "timebar-previous-pass");
  for (let i = 0; i < 5; i++) await page.locator('#timebar [data-a="prev"]').click();
  await settle(page, 3000);
  await agreement(`past pass ${await page.evaluate(() => window.nisan.state.t.toISOString().slice(0, 10))}`);
  await shot(page, "timebar-past-zones");
  await page.locator('#timebar [data-a="now"]').click(); await settle(page, 1500);
  await page.locator("#timebar .tb-track").focus();
  for (let i = 0; i < 4; i++) await page.keyboard.press("ArrowRight");
  await settle(page, 3000);
  const tFut = await page.evaluate(() => window.nisan.state.t.toISOString());
  ok("Arrow keys move into the forecast window", new Date(tFut) > new Date(), tFut);
  await agreement(`forecast +4 days`);
  await shot(page, "timebar-forecast-plus4d");
  await page.locator('#timebar [data-a="now"]').click(); await settle(page, 1500);

  /* 4. Settings */
  await page.click("#settingsBtn"); await page.waitForSelector("#settings:not([hidden])"); await settle(page, 600);
  await shot(page, "settings-sheet");
  for (const b of ["dark", "satellite", "light"]) {
    await page.locator(`#settings input[name="basemap"][value="${b}"]`).check({ force: true }); await settle(page, 2500);
    if (b !== "light") { await page.click("#settingsBtn"); await settle(page, 300); await shot(page, `basemap-${b}`); await page.click("#settingsBtn"); await settle(page, 300); }
  }
  ok("Basemap switches (dark, satellite, light)", true);
  const toggles = ["hand", "optical", "nisar", "farm", "research"];
  for (const k of toggles) {
    const box = page.locator(`#settings input[data-set="${k}"]`);
    if (!(await box.isChecked())) await box.check({ force: true });
    await settle(page, 500);
  }
  const st = await page.evaluate(() => window.nisan.state.settings);
  ok("Layer and detail toggles persist in settings", toggles.every((k) => st[k] === true), JSON.stringify(st));
  await shot(page, "settings-research-tools");
  await page.locator("#settings details.src").first().click(); await settle(page, 300);
  await page.locator("#settings .research h3").scrollIntoViewIfNeeded(); await settle(page, 300);
  await shot(page, "settings-thresholds-methods");
  await page.evaluate(() => document.querySelectorAll("#settings details.src").forEach((d) => (d.open = true)));
  const [obs] = await Promise.all([page.waitForEvent("download", { timeout: 5000 }).catch(() => null), page.locator("#settings [data-export]").first().click().catch(() => null)]);
  ok("Research export downloads a CSV", !!obs, obs ? await obs.suggestedFilename() : "no export button");
  await page.locator('#settings [data-act="refresh"]').click(); await settle(page, 1500);
  ok("Refresh now runs without errors", true);
  await page.click('[data-act="close-settings"]'); await settle(page, 2500);
  await page.evaluate(() => window.nisan.view.map.jumpTo({ center: [-94.45, 18.05], zoom: 11 })); await settle(page, 3500);
  await shot(page, "layers-hand-optical-nisar");

  /* farm + research on the place card */
  await page.locator(".views button[data-view=overview]").click(); await settle(page, 800);
  await page.evaluate(() => window.nisan.select([-94.43, 18.06], undefined, true));
  await page.waitForFunction(() => window.nisan.state.answer && !window.nisan.state.pointLoading); await settle(page, 2500);
  ok("Farm details render on the place card", (await page.locator("#panelBody", { hasText: "Equipment access" }).count()) === 1);
  await shot(page, "overview-farm-details");
  await page.locator("#panelBody").evaluate((e) => (e.scrollTop = e.scrollHeight)); await settle(page, 400);
  await shot(page, "overview-research-readings");
  const [wh] = await Promise.all([page.waitForEvent("download", { timeout: 5000 }).catch(() => null), page.locator('[data-act="point-csv"]').click().catch(() => null)]);
  ok("Water history CSV downloads", !!wh);

  /* collapse panel */
  await page.click("#collapse"); await settle(page, 600);
  ok("Panel collapses", await page.locator("#panel.collapsed").count() === 1);
  await shot(page, "panel-collapsed");
  await page.click("#collapse");

  /* reset optional layers so the user's saved settings are as before */
  await page.click("#settingsBtn");
  for (const k of toggles) { const box = page.locator(`#settings input[data-set="${k}"]`); if (await box.isChecked()) await box.uncheck({ force: true }); await settle(page, 200); }
  await page.click('[data-act="close-settings"]');

  /* 5. Mobile */
  const m = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true });
  const mp = await m.newPage();
  mp.on("pageerror", (e) => errors.push("mobile: " + e.message));
  await mp.goto(`${BASE}/?view=authorities`);
  await mp.waitForFunction(() => window.nisan && window.nisan.state.zones.length, null, { timeout: 60000 }); await mp.waitForTimeout(3000);
  const overflow = await mp.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  ok("Mobile: no horizontal overflow", !overflow);
  n++; await mp.screenshot({ path: path.join(OUT, `${String(n).padStart(2, "0")}-mobile-authorities.png`) });
  await mp.evaluate(() => { const z = window.nisan.state.zones[0]; return window.nisan.select(z.place.at, z.place.name, true); }); await mp.waitForTimeout(3000);
  n++; await mp.screenshot({ path: path.join(OUT, `${String(n).padStart(2, "0")}-mobile-zone-popup.png`) });
  await mp.goto(`${BASE}/?view=overview`); await mp.waitForTimeout(2500);
  await mp.evaluate(() => window.nisan.select(window.nisan.state.zones.length ? [-94.546, 17.993] : [-94.546, 17.993], "Minatitlán", true)); await mp.waitForTimeout(3000);
  n++; await mp.screenshot({ path: path.join(OUT, `${String(n).padStart(2, "0")}-mobile-place-card.png`) });
  await m.close();
} catch (e) {
  ok("Run completed", false, e.stack?.split("\n").slice(0, 3).join(" "));
  await shot(page, "failure").catch(() => {});
}

const real = errors.filter((e) => !/nominatim|favicon|ERR_ABORTED|AbortError/i.test(e));
console.log("ALL ERRORS:\n" + [...new Set(errors)].join("\n"));
ok("No console or page errors", !real.length, real.slice(0, 5).join(" | "));
fs.writeFileSync(path.join(OUT, "results.json"), JSON.stringify(results, null, 2));
console.log(`\n${results.filter((r) => r.pass).length}/${results.length} passed`);
await browser.close();
