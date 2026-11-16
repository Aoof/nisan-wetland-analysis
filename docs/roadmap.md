# Roadmap and open questions

## Before real use

- Threshold sign-off. Every threshold in [risk-model.md](risk-model.md) is provisional and needs review by a local civil protection or water authority before the Authorities view is shown to one.
- Zones. Which units do authorities work in: municipalities, colonias or watershed units? The current 11 places are a starting set.
- Check HAND against past floods. The 1, 5 and 15 m class breaks are generic.

## Data

- Full 30 m OPERA granules instead of the ≈107 m browse images (`opera.build_pass` is where they would plug in).
- NISAR water classes from the full GCOV product; today the layer is a backscatter image only.
- SWOT per-reach and per-lake series (RiverSP / LakeSP) in place of the basin-wide median.
- RADARSAT history through EODMS for the 30-year flood record.
- Long term: keep hosting processed rasters, or serve COGs through a tiler such as TiTiler.

## Beyond this basin

We built NISAN in two days as an MVP with one test area. Next we want to add more basins, get more out of the data each satellite collects, and study better ways to present it to people.

## App

- Spanish. The app is English only for now.
