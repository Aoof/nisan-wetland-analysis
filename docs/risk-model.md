# Risk model

We compute every risk level with a few fixed rules, all in [`nisan-app/src/fusion/risk.ts`](../nisan-app/src/fusion/risk.ts) and [`forecast.ts`](../nisan-app/src/fusion/forecast.ts). We don't use a trained model. Each level comes with the reasons that produced it, and the app shows the thresholds under Settings → Research tools.

All thresholds are provisional. They need sign-off from a local authority before the Authorities view is used for real decisions.

## Levels

`normal` → `watch` → `warning` → `emergency`. A level is always shown with its word as well as its colour.

## Hazard: what the water is doing

Three drivers each give a level:

| Driver | Quantity | Watch | Warning | Emergency |
|---|---|---|---|---|
| River flow | Forecast peak over the next 10 days ÷ GloFAS median for that day of year (2006–2025) | 1.5× | 2× | 3× |
| Rain | Forecast rain in the next 72 hours | 50 mm | 100 mm | 150 mm |
| Water seen by radar (zones only) | Share of the zone under water on the last pass, minus its usual share (median of earlier passes, needs 3 or more) | +7 pts | +15 pts | n/a |

Soil saturation is not a driver. Wet ground lowers the rain thresholds instead, because saturated soil sends more of the rain into runoff:

| Root-zone saturation | Rain thresholds become |
|---|---|
| under 75 % | unchanged |
| 75 % or more | 75 % of normal (watch at 37 mm) |
| 85 % or more | 50 % of normal (watch at 25 mm) |

Saturation comes from SMAP L4 when a value from the last 5 days exists, otherwise from the ECMWF model soil moisture.

The hazard is the highest driver level. When two or more drivers are above normal at once, it goes up one step (up to emergency at most).

## Exposure: how low the ground is

Exposure comes from HAND, the height above the nearest drainage, derived from the Copernicus GLO-30 DEM:

| HAND class | Height above drainage | Meaning |
|---|---|---|
| 1 | 0–1 m | floods first |
| 2 | 1–5 m | floods in bigger events |
| 3 | 5–15 m | floods only in extreme events |
| 4 | over 15 m | well above local drainage |

### Zones (the 11 named places)

Zone level = hazard, lowered one step when less than 15 % of the zone is low ground (HAND classes 1 and 2). A normal hazard stays normal. The Authorities list also computes the level 24 hours earlier and marks zones that rose.

### Any other point

The hazard uses the nearest gauge and the nearest place's weather, then shifts by the point's HAND class:

| Class | Result |
|---|---|
| 1 | hazard + 1 step |
| 2 | hazard |
| 3 | hazard − 1 step (normal stays normal) |
| 4 | normal, or watch if the hazard is emergency |

If the last clear radar look shows water at a spot that is usually dry, the level is at least warning.

A spot seen wet in 60 % or more of at least 5 clear radar looks is labelled "usually under water: wetland, lagoon or river" instead of getting a flood headline.

A selection made from a zone (the list, a pin, a search result for a named place) shows the zone's verdict everywhere: the place card, the map popup and the zone list. The pin's own terrain is added as detail.

## Basin signals (Authorities view)

- Each river gauge: its 10-day peak ratio, using the river-flow thresholds.
- Each place with rain above normal (soil-adjusted).
- Basin surface water: inland water area on the last radar pass with at least 50 % of the area observed, compared with the median of earlier passes (needs 4 or more). Watch at +15 %, warning at +30 %, emergency at +50 %.

## Outputs

- Brief: a plain-text summary of the zones above normal and the top signals, timestamped in Central Mexico time. Copy it from the Authorities view.
- Zones CSV: one row per zone with its level, previous level and reasons.
- Research exports: acquisitions and series CSVs per source, under Settings → Research tools.

## Known limits

- GloFAS is a ~5 km model: it covers the main rivers, not urban drains or small creeks.
- HAND is computed on surface heights, so roofs and canopy raise it in towns and forests.
- SMAP cells are 9 km: a regional signal, not a field or a street.
- Wind-roughened water can look dry to C-band radar.
- NISAR water classes are not produced yet; the layer is a backscatter image.
