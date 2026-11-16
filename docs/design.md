# NISAN design contract

NISAN is a public-service hazard map. People open it to find out whether water is coming to their street or their district. It should read like a flood bulletin laid over a calm map: plain, legible, and loud only when the risk is.

## Direction

- Voice: we write like a government bulletin. Sentence-case labels, no slogans, no decorative icons.
- Colour carries meaning. The interface is neutral, and colour appears only for risk level and for water.
- The one signature detail is the time bar, which is drawn like a river-gauge strip. Satellite passes are tick marks, "now" is the waterline, and the forecast is hatched.
- Overview and Authorities share every token below. Authorities adds a status band in the current risk colour.

## Tokens

| Role | Value |
|---|---|
| Ground | `#F6F7F5` |
| Paper (panels) | `#FFFFFF` |
| Ink | `#1B2430` |
| Secondary ink (AA on paper) | `#4A5563` |
| Rule | `#D8DCD6` |
| Water | `#2F6DB5` |
| Water under vegetation | `#16A085` |
| Normal / Watch / Warning / Emergency | `#2E7D32` / `#B7791F` / `#D9622B` / `#C62828` |

Type: **Public Sans** (400, 500, 600, 700), tabular numbers everywhere. Base 15 px / 1.5. Panel headings 14 px semibold in secondary ink; answers 19 px semibold.

Shape: 6 px radius, 1 px rule borders, no shadows, no blur. Spacing steps of 4 px; panel padding 16 px.

## Rules

1. Risk colour is never the only signal: every level also has its word.
2. Every number that can go stale shows its age.
3. The most important answer is first. Anything for specialists lives in Settings and stays off until asked for.
4. Map data sits under place labels so names stay readable.
5. Respect `prefers-reduced-motion`; keyboard focus is always visible (`:focus-visible`).
6. English only.
7. Only one dialog interrupts the map: "About NISAN" (`src/ui/intro.ts`). It opens on a first visit and stays closed once the viewer ticks "Don't show this again". Settings → About reopens it.
