"""Search, order and download RADARSAT scenes over the AOI from Canada's EODMS.

    python fetch_radarsat.py search rcm                  # list scenes, write CSV + JSON
    python fetch_radarsat.py search r1 --start 1995-01-01 --end 2013-12-31
    python fetch_radarsat.py order rcm --max 3           # order the first 3 scenes in the last search
    python fetch_radarsat.py order rcm --ids 1234567,1234568
    python fetch_radarsat.py download rcm                # wait for orders, then download

EODMS ordering is asynchronous: an order can take minutes to hours to be
ready. `download` polls until the order is complete.

Credentials come from EODMS_USERNAME / EODMS_PASSWORD, or you are prompted.
These are EODMS credentials, not NASA Earthdata ones.
"""
import argparse
import getpass
import json
import os
import sys

import config


def client():
    from eodms_rapi import EODMSRAPI

    user = os.environ.get("EODMS_USERNAME") or input("EODMS username: ")
    pwd = os.environ.get("EODMS_PASSWORD") or getpass.getpass("EODMS password: ")
    return EODMSRAPI(user, pwd)


def paths(key):
    out = config.OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    stem = out / f"{config.AOI_NAME}_{key}"
    return {"results": f"{stem}_search.json", "csv": f"{stem}_search.csv", "orders": f"{stem}_orders.json"}


def search(rapi, key, start, end, max_results):
    import pandas as pd

    dates = [{"start": start.replace("-", "") + "_000000", "end": end.replace("-", "") + "_235959"}]
    rapi.search(config.COLLECTIONS[key], features=[("intersects", config.bbox_wkt())],
                dates=dates, max_results=max_results)
    res = rapi.get_results("full") or []
    p = paths(key)
    with open(p["results"], "w") as f:
        json.dump(res, f, indent=1, default=str)
    if res:
        df = pd.json_normalize(res)
        df.to_csv(p["csv"], index=False)
        keep = [c for c in df.columns if any(k in c.lower() for k in ("recordid", "title", "start", "beam", "polar"))]
        print(df[keep[:6]].head(20).to_string(index=False))
    print(f"{len(res)} scenes. Wrote {p['results']} and {p['csv']}")


def order(rapi, key, max_items, ids):
    p = paths(key)
    if not os.path.exists(p["results"]):
        sys.exit("Run `search` first")
    with open(p["results"]) as f:
        res = json.load(f)
    if ids:
        wanted = {i.strip() for i in ids.split(",")}
        res = [r for r in res if str(r.get("recordId")) in wanted]
    res = res[:max_items]
    if not res:
        sys.exit("Nothing to order")
    print(f"Ordering {len(res)} scenes from {config.COLLECTIONS[key]}...")
    order_res = rapi.order(res)
    with open(p["orders"], "w") as f:
        json.dump(order_res, f, indent=1, default=str)
    print(f"Order submitted. Saved {p['orders']}; run `download {key}` to fetch when ready.")


def download(rapi, key):
    p = paths(key)
    if not os.path.exists(p["orders"]):
        sys.exit("Run `order` first")
    with open(p["orders"]) as f:
        order_res = json.load(f)
    dest = config.RAW_DIR / key
    dest.mkdir(parents=True, exist_ok=True)
    rapi.download(order_res, str(dest))
    print(f"Downloaded to {dest}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["search", "order", "download"])
    ap.add_argument("collection", choices=sorted(config.COLLECTIONS))
    ap.add_argument("--start", default=config.DEFAULT_START)
    ap.add_argument("--end", default=config.DEFAULT_END)
    ap.add_argument("--max-results", type=int, default=500, help="search: cap on results")
    ap.add_argument("--max", type=int, default=1, help="order: how many scenes from the search (default 1)")
    ap.add_argument("--ids", help="order: comma-separated recordIds instead of the first --max")
    args = ap.parse_args()

    rapi = client()
    if args.action == "search":
        search(rapi, args.collection, args.start, args.end, args.max_results)
    elif args.action == "order":
        order(rapi, args.collection, args.max, args.ids)
    else:
        download(rapi, args.collection)


if __name__ == "__main__":
    main()
