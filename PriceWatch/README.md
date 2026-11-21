# PriceWatch

Track the price of any product, plus per-size stock when the store shows it.
Alerts arrive as texts sent from this Mac's Messages app.

## Start
Run `prices` in Terminal (or `./start.sh` in the InventoryCheck folder).
It opens **http://pricewatch.localhost:8503** in your browser.
Other commands: `prices restart` (after code changes), `prices stop`, `prices log`.
While automatic checks are on, the page also starts by itself at login.
Everyday tasks, including how to pause the checks, are in the cheat sheet: [HOW-TO.md](../HOW-TO.md).

The Python environment lives in `.venv.nosync`, which iCloud Drive doesn't sync, and `.venv` is a
symlink to it. If the environment is missing, `start.sh` rebuilds it.

## One-time setup for texts
1. Add your cell number to `../.env`: `ALERT_PHONE=+1XXXXXXXXXX`, then `prices restart`.
2. If iMessage isn't available, turn on iPhone Settings → Apps → Messages → Text Message Forwarding for this Mac,
   so the Mac can send a regular SMS over your AT&T line.
3. On the page, click **Send a test text**. The first time, macOS asks whether PriceWatch may control
   Messages. Allow it.

## Using the page
- **Check a product:** paste any product link. The page shows whether it can be tracked, the price,
  and the sizes/options. Click a size, optionally set a "text me below $" price, then click **Track it**.
- **Compare stores:** track the same product from another store under the same name. The
  watchlist marks the cheapest store, and texts include it.
- **Search a store:** searches Shopify stores (store.ussoccer.com, many brand/team shops) without a browser.
- **Check automatically:** choose how often. This runs in the background (launchd) even when the page is closed.
  Log: `PriceWatch/logs/pricewatch.log`.
- Stores that block automated price checks (Amazon, Walmart, Target, Dick's usually do) say so when you
  paste a link. For Amazon, use camelcamelcamel.com's own alerts.

Every text starts with a label line (default `🧪 SPODG Labs PriceWatch`) so it stands out in your Messages thread.
To change it, set `ALERT_LABEL=...` in `.env`; to turn it off, set `ALERT_LABEL=` (empty). Then run `prices restart`.

## What triggers a text
- A price drops, reaches your target, or your size comes back in stock (sent right away)
- A store can't be read several checks in a row, and again when it's working ("Problem alerts")
- A summary of each item's best price, which also confirms PriceWatch is still running.
  If the Mac is off on summary day, it arrives at the next check.

Set the summary (on/off, weekly or daily, day, time) and the problem alerts in the
**Texts & schedule** section of the page. They're saved in `settings.json` and apply on the next
check, with no restart needed. `.env` holds only private things: `ALERT_PHONE` and `ALERT_LABEL`.

## Checking while the Mac is asleep
A sleeping Mac doesn't run the daily check; it runs once the Mac wakes. To have the Mac wake itself
for it (like Task Scheduler's "wake the computer to run this task"), run this once in Terminal:
```
sudo pmset repeat wakeorpoweron MTWRFSU 07:59:00
```
The check holds the Mac awake until it finishes (`caffeinate`), then the Mac goes back to sleep.
If you change the summary time on the page, change `07:59:00` to one minute before it.
`pmset -g sched` shows the wake; `sudo pmset repeat cancel` removes it.

## Command line (same features)
`.venv/bin/python PriceWatch/pricewatch.py probe|add|search|list|check|history|remove|test-text|install|uninstall`
