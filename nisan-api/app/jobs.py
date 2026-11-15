"""Background refresh. Everything here is best-effort: the API answers from the last good copy
while a job runs, and a failed job only changes a status message."""
import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .sources import dem, earthdata, forecast, nisar, opera
from .store import set_status

scheduler = AsyncIOScheduler()


async def warm() -> None:
    if dem.available():
        await asyncio.to_thread(dem.grids)
        set_status("dem-hand", "live", "Terrain layers ready")
    else:
        set_status("dem-hand", "unavailable", "Run data-sources/copernicus-dem-sandbox/fetch_dem.py")


async def startup() -> None:
    """Order = what the first screen needs first: forecast + terrain, then the latest water map, then the rest."""
    set_status("radarsat", "unavailable", "Needs an EODMS account and SAR processing; not wired yet.")
    await asyncio.gather(forecast.refresh(), warm())
    await opera.refresh("opera-dswx-s1")
    await asyncio.gather(opera.refresh("opera-dswx-hls"), nisar.refresh())
    for s in ("smap-l4", "swot-raster"):
        await earthdata.refresh(s)


def start() -> None:
    scheduler.add_job(forecast.refresh, "interval", hours=1, id="forecast", max_instances=1, coalesce=True)
    scheduler.add_job(opera.refresh, "interval", hours=3, args=["opera-dswx-s1"], id="s1", max_instances=1, coalesce=True)
    scheduler.add_job(opera.refresh, "interval", hours=3, args=["opera-dswx-hls"], id="hls", max_instances=1, coalesce=True)
    scheduler.add_job(nisar.refresh, "interval", hours=6, id="nisar", max_instances=1, coalesce=True)
    scheduler.add_job(earthdata.refresh, "interval", hours=12, args=["smap-l4"], id="smap", max_instances=1, coalesce=True)
    scheduler.add_job(earthdata.refresh, "interval", hours=24, args=["swot-raster"], id="swot", max_instances=1, coalesce=True)
    scheduler.start()
