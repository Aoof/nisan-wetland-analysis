/**
 * "About NISAN" dialog. Shown on a first visit; "Don't show this again" is remembered in this browser.
 * It can always be reopened from Settings → About.
 */

const KEY = "nisan-intro-v1";

function dismissed(): boolean {
  try { return localStorage.getItem(KEY) === "dismissed"; } catch { return false; }
}
function remember(hide: boolean): void {
  try { hide ? localStorage.setItem(KEY, "dismissed") : localStorage.removeItem(KEY); } catch { /* blocked storage: show again next time */ }
}

const PITCH = [
  "Several satellites watch this basin. Some use radar that sees water through cloud or under trees, others measure how wet the soil is or how high rivers and lagoons stand, and forecasts add the rain and river flow still to come. Each one tells part of the story. NISAN brings them together on one map that anyone can read.",
  "The same information serves different people. Someone living near the river may need to know whether to act now. A farmer may want an educated guess about when the ground is ready to plant. A researcher may want the readings themselves. Wherever you tap, NISAN starts with a plain answer and the reasons behind it, and the full detail is there for anyone who wants it.",
  "We keep the rules simple so you can see, understand and pass on why an area is marked the way it is. Places that are wet most of the year are shown as wetland, lagoon or river so they don't raise false alarms, and every reading shows its age because some satellites only pass every few days or weeks.",
  "We built NISAN in two days for the NASA Space Apps Challenge, so it covers one test area: the lower Coatzacoalcos basin, where our team has personal ties, floods are frequent, and cities, farms and wetlands sit side by side. Next we want to add more basins and get more out of each satellite.",
];

export function initIntro(): { open: () => void } {
  const dlg = document.createElement("dialog");
  dlg.className = "intro";
  dlg.setAttribute("aria-labelledby", "introTitle");
  dlg.innerHTML = `
    <form method="dialog">
      <h2 id="introTitle" tabindex="-1" autofocus>Welcome to NISAN</h2>
      <p class="lead">NISAN is a flood and wetland map for the lower Coatzacoalcos basin in Veracruz, Mexico. Search for a place or tap anywhere on the map to see whether water is likely to reach it in the next few days, why, and what to do. You can also look back over the last four months to see how the area's rivers, lagoons and wetlands have grown and shrunk, as seen from space.</p>
      ${PITCH.map((p) => `<p>${p}</p>`).join("")}
      <p class="note">NISAN isn't an official warning service. In an emergency, follow your local civil protection instructions.</p>
      <div class="intro-foot">
        <label class="opt"><input type="checkbox" id="introHide" /><span>Don't show this again</span></label>
        <button class="btn primary" value="ok">Got it</button>
      </div>
    </form>`;
  document.body.append(dlg);
  const hide = dlg.querySelector<HTMLInputElement>("#introHide")!;

  // Esc, the button and a click on the backdrop all close it; the checkbox decides whether it comes back.
  dlg.addEventListener("close", () => remember(hide.checked));
  dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });

  const open = () => { hide.checked = dismissed(); if (!dlg.open) dlg.showModal(); };
  if (!dismissed()) open();
  return { open };
}
