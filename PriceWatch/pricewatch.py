#!/usr/bin/env python3
"""PriceWatch - track price and stock for any product URL, alert by text from this Mac.

Easiest: run ./start.sh in the project folder and use the web page.

Command line (same features):
  python pricewatch.py probe URL [--size XL]          see what can be read from a page
  python pricewatch.py add URL --name "Home Jersey" [--size XL] [--target 90]
                                                      (same --name again = track another store)
  python pricewatch.py search store.ussoccer.com "stadium jersey"   find products on a Shopify store
  python pricewatch.py list | check [--dry-run] | history NAME | remove NAME [--url URL]
  python pricewatch.py test-text
  python pricewatch.py install [--every 30] | uninstall
"""
from __future__ import annotations

import argparse
import json
import os
import plistlib
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from extract import UA, fetch, size_status  # noqa: E402
from notify import send_text  # noqa: E402

load_dotenv(HERE / ".env")
load_dotenv(HERE.parent / ".env")

WATCHLIST = HERE / "watchlist.json"
DB = HERE / "prices.db"
STATE = HERE / "state.json"
LOGS = HERE / "logs"
LABEL = "com.pricewatch.check"
PLIST = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
# Always the project's .venv (a symlink to .venv.nosync, which iCloud doesn't sync)
VENV_PYTHON = HERE.parent / ".venv" / "bin" / "python"
DIGEST_HOUR = int(os.getenv("DIGEST_HOUR", "8"))


# ================================================================ storage
def load_list() -> dict:
    if WATCHLIST.exists():
        return json.loads(WATCHLIST.read_text())
    return {"items": []}


def save_list(data: dict) -> None:
    WATCHLIST.write_text(json.dumps(data, indent=2) + "\n")


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS obs (
        ts TEXT, item TEXT, url TEXT, price REAL, available INTEGER, method TEXT, title TEXT)""")
    return con


def last_obs(con, item: str, url: str, readable_only: bool = True):
    where = " AND price IS NOT NULL" if readable_only else ""
    return con.execute(
        f"SELECT price, available, ts FROM obs WHERE item=? AND url=?{where} "
        "ORDER BY rowid DESC LIMIT 1", (item, url)).fetchone()


def store_name(url: str) -> str:
    return urlparse(url).netloc.replace("www.", "")


def avail_value(a):
    return None if a is None else bool(a)


def fmt_avail(a) -> str:
    return {True: "in stock", False: "SOLD OUT", None: "stock unknown"}[a]


def record(con, item: str, url: str, price, avail, method, title) -> None:
    con.execute("INSERT INTO obs VALUES (?,?,?,?,?,?,?)",
                (datetime.now().isoformat(timespec="seconds"), item, url, price,
                 None if avail is None else int(avail), method, title))


# ================================================================ core actions
# (used by both the command line and the web page)
def add_url(url: str, name: str, size: Optional[str] = None,
            target: Optional[float] = None, res: Optional[dict] = None) -> dict:
    """Track url under item `name`. Raises ValueError if no price can be read."""
    res = res or fetch(url)
    if not res:
        raise ValueError("Couldn't read a price from that page.")
    data = load_list()
    item = next((i for i in data["items"] if i["name"].lower() == name.lower()), None)
    if item is None:
        item = {"name": name, "size": size or None, "target": target, "urls": []}
        data["items"].append(item)
    else:
        if size:
            item["size"] = size
        if target is not None:
            item["target"] = target
    if not any(u["url"] == url for u in item["urls"]):
        item["urls"].append({"url": url, "method": res["method"]})
    save_list(data)
    a, p = size_status(res, item.get("size"))
    with db() as con:
        record(con, item["name"], url, p, a, res["method"], res["title"])
    return {"name": item["name"], "store": store_name(url), "price": p, "available": a,
            "method": res["method"]}


def remove_item(name: str, url: Optional[str] = None) -> bool:
    data = load_list()
    for it in data["items"]:
        if it["name"].lower() == name.lower():
            if url:
                it["urls"] = [u for u in it["urls"] if u["url"] != url]
                if not it["urls"]:
                    data["items"].remove(it)
            else:
                data["items"].remove(it)
            save_list(data)
            return True
    return False


def watchlist_status() -> List[dict]:
    """Watchlist plus each store's latest reading."""
    con = db()
    out = []
    for it in load_list()["items"]:
        stores = []
        for u in it["urls"]:
            ok = last_obs(con, it["name"], u["url"])
            latest = last_obs(con, it["name"], u["url"], readable_only=False)
            stores.append({
                "url": u["url"], "store": store_name(u["url"]), "method": u.get("method"),
                "price": ok[0] if ok else None,
                "available": avail_value(ok[1]) if ok else None,
                "checked": latest[2] if latest else None,
                "failing": bool(latest and latest[0] is None),
            })
        buyable = [s for s in stores if s["price"] is not None and s["available"] is not False]
        best = min(buyable, key=lambda s: s["price"]) if buyable else None
        out.append({**{k: it.get(k) for k in ("name", "size", "target")},
                    "stores": stores, "best": best["store"] if best else None})
    return out


def history(name: str) -> List[dict]:
    rows = db().execute(
        "SELECT ts, url, price, available FROM obs WHERE lower(item)=lower(?) ORDER BY rowid",
        (name,)).fetchall()
    return [{"ts": ts, "store": store_name(url), "price": p, "available": avail_value(a)}
            for ts, url, p, a in rows]


def search_shopify(store: str, query: str) -> List[dict]:
    """Shopify's built-in product search - works on any Shopify store.
    Raises ValueError if the site isn't a Shopify store."""
    domain = store.replace("https://", "").replace("http://", "").strip("/")
    r = requests.get(f"https://{domain}/search/suggest.json",
                     params={"q": query, "resources[type]": "product", "resources[limit]": 10},
                     headers={"User-Agent": UA}, timeout=20)
    if r.status_code != 200 or "json" not in r.headers.get("content-type", ""):
        raise ValueError(f"{domain} doesn't look like a Shopify store, so it can't be searched here. "
                         "Find the product in your browser and paste its link instead.")
    prods = r.json().get("resources", {}).get("results", {}).get("products", [])
    return [{"title": p["title"], "price": p.get("price"), "available": p.get("available"),
             "url": f"https://{domain}{p['url'].split('?')[0]}"} for p in prods]


def run_check(dry_run: bool = False, log: Callable[[str], None] = print) -> None:
    """Check every tracked URL once and text any alerts. This is what the schedule runs."""
    data = load_list()
    con = db()
    changed = False
    for it in data["items"]:
        alerts, best = [], None
        for u in it["urls"]:
            store = store_name(u["url"])
            res = fetch(u["url"], preferred=u.get("method"))
            if not res:
                log(f"⚠️  {it['name']} @ {store}: could not read price")
                record(con, it["name"], u["url"], None, None, None, None)
                continue
            if res["method"] != u.get("method"):
                u["method"] = res["method"]
                changed = True
            avail, price = size_status(res, it.get("size"))
            prev = last_obs(con, it["name"], u["url"])
            record(con, it["name"], u["url"], price, avail, res["method"], res["title"])
            log(f"   {it['name']} @ {store}: ${price:.2f} {fmt_avail(avail)}")

            buyable = avail is not False
            if buyable and (best is None or price < best[0]):
                best = (price, u["url"])
            target = it.get("target")
            if prev:
                prev_price, prev_avail, _ = prev
                if avail is True and prev_avail == 0:
                    alerts.append(f"BACK IN STOCK at {store}: ${price:.2f}")
                if buyable and price < prev_price - 0.5:
                    alerts.append(f"Price drop at {store}: ${prev_price:.2f} → ${price:.2f}")
                if buyable and target and price <= target < prev_price:
                    alerts.append(f"Hit your ${target:g} target at {store}: ${price:.2f}")
            elif buyable and target and price <= target:
                alerts.append(f"At/below your ${target:g} target at {store}: ${price:.2f}")
            time.sleep(2)

        if alerts:
            size = f" ({it['size']})" if it.get("size") else ""
            msg = f"🔔 {it['name']}{size}\n" + "\n".join(alerts)
            if best:
                msg += f"\nBest: ${best[0]:.2f} {best[1]}"
            log(msg)
            send_text(msg, dry_run=dry_run)
    con.commit()
    if changed:
        save_list(data)
    maybe_digest(con, data, dry_run)


def maybe_digest(con, data, dry_run: bool) -> None:
    """Once a day after DIGEST_HOUR: a summary text, which doubles as 'still running' heartbeat."""
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    today = datetime.now().strftime("%Y-%m-%d")
    if datetime.now().hour < DIGEST_HOUR or state.get("digest") == today or not data["items"]:
        return
    lines = ["☀️ Daily summary"]
    for it in watchlist_status():
        buyable = [s for s in it["stores"] if s["price"] is not None and s["available"] is not False]
        best = min(buyable, key=lambda s: s["price"]) if buyable else None
        line = f"• {it['name']}: " + (f"${best['price']:.2f} @ {best['store']}" if best else "not available")
        broken = sum(s["failing"] for s in it["stores"])
        if broken:
            line += f" (⚠️ {broken} store(s) unreadable)"
        lines.append(line)
    send_text("\n".join(lines), dry_run=dry_run)
    state["digest"] = today
    STATE.write_text(json.dumps(state))


# ================================================================ schedule (launchd)
DAILY = 1440  # minutes; "once a day" runs at DIGEST_HOUR instead of every 24h from install


def install_schedule(every: int) -> str:
    LOGS.mkdir(exist_ok=True)
    if every >= DAILY:
        # A fixed time of day; launchd runs it on wake if the Mac was asleep then
        timing = {"StartCalendarInterval": {"Hour": DIGEST_HOUR, "Minute": 0}}
        when = f"once a day at {datetime.now().replace(hour=DIGEST_HOUR, minute=0):%-I:%M %p}"
    else:
        timing = {"StartInterval": every * 60}
        when = f"every {every} minutes"
    plist = {
        "Label": LABEL,
        "ProgramArguments": [str(VENV_PYTHON), str(HERE / "pricewatch.py"), "check"],
        **timing,
        "RunAtLoad": True,
        "WorkingDirectory": str(HERE),
        "StandardOutPath": str(LOGS / "pricewatch.log"),
        "StandardErrorPath": str(LOGS / "pricewatch.log"),
    }
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
    with open(PLIST, "wb") as f:
        plistlib.dump(plist, f)
    subprocess.run(["launchctl", "load", str(PLIST)], check=True, capture_output=True)
    return f"Checking {when}. Log: {LOGS / 'pricewatch.log'}"


def uninstall_schedule() -> str:
    subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
    PLIST.unlink(missing_ok=True)
    return "Schedule removed."


def schedule_status() -> Optional[int]:
    """Minutes between scheduled checks, or None if not scheduled."""
    if not PLIST.exists():
        return None
    with open(PLIST, "rb") as f:
        p = plistlib.load(f)
    return DAILY if "StartCalendarInterval" in p else p.get("StartInterval", 0) // 60


# ================================================================ command line
def cmd_probe(args) -> None:
    print(f"Probing {args.url} ...")
    res = fetch(args.url)
    if not res:
        print("❌ Couldn't find a price on this page with any method.\n"
              "   This site probably blocks automated access (Amazon, Walmart, Target often do).\n"
              "   Try the same product at a different store.")
        return
    print(f"✅ Readable via: {res['method']}")
    print(f"   Title: {res['title']}")
    print(f"   Price: {res['price']} {res['currency'] or ''}   ({fmt_avail(res['in_stock'])})")
    if res["sizes"]:
        print("   Sizes / variants:")
        for label, info in res["sizes"].items():
            print(f"     - {label:<30} {info.get('price')}  {fmt_avail(info.get('available'))}")
    else:
        print("   (No per-size stock on this page - only the overall price can be tracked.)")
    if args.size:
        a, p = size_status(res, args.size)
        print(f"   Size {args.size}: {p} - {fmt_avail(a)}")


def cmd_add(args) -> None:
    try:
        r = add_url(args.url, args.name, args.size, args.target)
    except ValueError as e:
        print(f"❌ {e} Not added. Run `probe` for details.")
        return
    print(f"✅ Tracking '{r['name']}' at {r['store']}: ${r['price']} "
          f"({fmt_avail(r['available'])}) via {r['method']}")


def cmd_list(args) -> None:
    items = watchlist_status()
    if not items:
        print("Watchlist is empty. Use `add`.")
    for it in items:
        tgt = f"  target ≤ ${it['target']:g}" if it.get("target") else ""
        print(f"\n■ {it['name']}  size={it.get('size') or 'any'}{tgt}")
        for s in it["stores"]:
            last = f"${s['price']:.2f} {fmt_avail(s['available'])}" if s["price"] is not None else "no data yet"
            print(f"   - {s['store']:<28} {last:<28} [{s['method']}]  {s['url']}")


def cmd_remove(args) -> None:
    print("Removed." if remove_item(args.name, args.url) else "No item by that name.")


def cmd_history(args) -> None:
    for h in history(args.name):
        p = f"${h['price']:.2f}" if h["price"] is not None else "  (failed)"
        print(f"{h['ts']}  {h['store']:<28} {p:>10}  {fmt_avail(h['available'])}")


def cmd_search(args) -> None:
    try:
        results = search_shopify(args.store, args.query)
    except ValueError as e:
        print(f"❌ {e}")
        return
    if not results:
        print("No results.")
    for p in results:
        print(f"${p['price'] or '?':>8}  {'✓' if p['available'] else '✗'}  {p['title']}\n"
              f"           {p['url']}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Track prices on any store.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("probe", help="show what PriceWatch can read from a URL")
    p.add_argument("url"); p.add_argument("--size")
    p.set_defaults(fn=cmd_probe)

    p = sub.add_parser("add", help="track a URL (same --name again adds another store)")
    p.add_argument("url"); p.add_argument("--name", required=True)
    p.add_argument("--size"); p.add_argument("--target", type=float)
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("search", help="search a Shopify store's products")
    p.add_argument("store"); p.add_argument("query")
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("check", help="check everything once (what the schedule runs)")
    p.add_argument("--dry-run", action="store_true", help="print alerts instead of texting")
    p.set_defaults(fn=lambda a: run_check(a.dry_run))

    sub.add_parser("list").set_defaults(fn=cmd_list)
    p = sub.add_parser("history"); p.add_argument("name"); p.set_defaults(fn=cmd_history)
    p = sub.add_parser("remove"); p.add_argument("name"); p.add_argument("--url")
    p.set_defaults(fn=cmd_remove)
    sub.add_parser("test-text").set_defaults(
        fn=lambda a: send_text("✅ Test message from your Mac"))
    p = sub.add_parser("install", help="run `check` on a schedule via launchd")
    p.add_argument("--every", type=int, default=30,
                   help="minutes between checks (1440 = once a day at DIGEST_HOUR)")
    p.set_defaults(fn=lambda a: print("✅ " + install_schedule(a.every)))
    sub.add_parser("uninstall").set_defaults(fn=lambda a: print(uninstall_schedule()))

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
