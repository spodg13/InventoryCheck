# PriceWatch

Track the price of any product, plus per-size stock when the store shows it.
Alerts arrive as texts sent from this Mac's Messages app.

## Start
Run `./start.sh` in the InventoryCheck folder (or `prices`, once the alias below is added).
It opens **http://pricewatch.localhost:8503** in your browser.
Other commands: `prices restart` (after code changes), `prices stop`, `prices log`.

Shortcut: add this line to `~/.zshrc`:
```
alias prices='"/Users/darrylgould/Library/Mobile Documents/com~apple~CloudDocs/Coding/InventoryCheck/start.sh"'
```

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

Every text starts with a `🧪 SpodgLabs PriceWatch` line so it stands out in your Messages thread.
To change it, set `ALERT_LABEL=...` in `.env`; to turn it off, set `ALERT_LABEL=` (empty). Then run `prices restart`.

## What triggers a text
- A price drops, reaches your target, or your size comes back in stock (sent right away)
- A store can't be read several checks in a row, and again when it's working ("Problem alerts")
- A summary of each item's best price, which also confirms PriceWatch is still running.
  If the Mac is off on summary day, it arrives at the next check.

Set the summary (on/off, weekly or daily, day, time) and the problem alerts in the
**Texts & schedule** section of the page. They're saved in `settings.json` and apply on the next
check, with no restart needed. `.env` holds only private things: `ALERT_PHONE` and `ALERT_LABEL`.

## Command line (same features)
`.venv/bin/python PriceWatch/pricewatch.py probe|add|search|list|check|history|remove|test-text|install|uninstall`
