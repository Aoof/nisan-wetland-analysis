# radarsat-sandbox

Search, order and download RADARSAT scenes over Coatzacoalcos from **Canada's EODMS** catalogue. RADARSAT is not on NASA Earthdata. ASF's RADARSAT-1 archive has no scenes over this AOI, because it mostly covers Alaska and Antarctica.

| Key | Collection | Notes |
|---|---|---|
| `rcm` | `RCMImageProducts` | RADARSAT Constellation Mission, C-band, 2019 onward |
| `r1` | `Radarsat1` | RADARSAT-1 archive, C-band HH, 1995–2013. Long history for the baseline. |

## Setup and run

1. Create an EODMS account at eodms-sgdot.nrcan-rncan.gc.ca. This is separate from Earthdata.
2. Set up the environment and run:

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
export EODMS_USERNAME=...   # or be prompted
.venv/bin/python fetch_radarsat.py search rcm
.venv/bin/python fetch_radarsat.py search r1 --start 1995-01-01 --end 2013-12-31
.venv/bin/python fetch_radarsat.py order rcm --max 2
.venv/bin/python fetch_radarsat.py download rcm
```

`search` writes `data/processed/*_search.csv` and `*_search.json`. `order` submits the first `--max` scenes, or the scenes given with `--ids`. `download` waits until the order is ready, then saves it to `data/raw/<collection>/`.

## Caveats

- **Untested.** EODMS refuses even a catalogue listing without an account, so these scripts have never been run against the live service. The calls follow the `py-eodms-rapi` documentation.
- **Access limits.** RCM imagery may be restricted, depending on your account type. Non-Canadian-government users may see scenes but be unable to order them. RCM also images mostly Canada, so coverage of Mexico may be sparse. RADARSAT-1 archive data is open.
- **Raw downloads.** Downloads are raw SAR products: RCM GRD/SLC, or RADARSAT-1 path images. They are not yet terrain-corrected, and turning them into water maps needs SAR processing, for example ESA SNAP. This sandbox stops at the download.
- **Slow orders.** Orders are queued on EODMS's side and can take hours. Start with `--max 1`.
- **Alternative L-band history.** ASF does have **ALOS-1 PALSAR** L-band scenes, 2007–2011, already terrain-corrected (`RTC_HI_RES`), over this AOI. They are a closer historical match for NISAR than RADARSAT's C-band, and come with a normal Earthdata login.
