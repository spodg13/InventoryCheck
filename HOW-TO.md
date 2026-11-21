# PriceWatch cheat sheet

PriceWatch has two parts that run separately:

- **The daily price check** runs in the background at 8:00 AM, texts you, and survives restarts on its own.
- **The page** (http://pricewatch.localhost:8503) is just for looking and changing things.
  While automatic checks are on, it starts by itself when you log in. Nothing breaks while it's off.

Type these commands in Terminal. `prices` works from any folder.

## The page
| I want to… | Do this |
|---|---|
| Open the page (starts it if needed) | `prices` |
| Stop the page | `prices stop` |
| Restart it (after changing `.env` or the code) | `prices restart` |
| See why it won't start | `prices log` |

Stopping the page does **not** stop the daily price checks or texts. It stays stopped until you run
`prices` or log in again.

## The daily price check
| I want to… | Do this |
|---|---|
| Pause all checks and texts | On the page: **Texts & schedule → Check automatically → Off** (the page also stops starting at login) |
| Turn them back on | Same menu → **Once a day** (or another interval) |
| Check prices right now | On the page: **Check prices now** |
| See what the last checks found | Open `PriceWatch/logs/pricewatch.log` |
| Change the summary text (day, time, on/off) | On the page: **Texts & schedule → Summary text** |

Without the page, from the InventoryCheck folder:
`.venv/bin/python PriceWatch/pricewatch.py uninstall` pauses checks, and
`.venv/bin/python PriceWatch/pricewatch.py install --every 1440` turns them back on (once a day).

## The 7:59 AM wake
The Mac wakes itself one minute before the check, then goes back to sleep.

| I want to… | Do this |
|---|---|
| See if the wake is set | `pmset -g sched` (look under "Repeating power events") |
| Turn the wake off | `sudo pmset repeat cancel` |
| Turn it back on | `sudo pmset repeat wakeorpoweron MTWRFSU 07:59:00` |

If you change the summary time on the page, set the wake to one minute before it.

## Watching things
| I want to… | Do this |
|---|---|
| Track a new product | Paste its link into **Check a product**, then click **Track it** |
| Compare the same product at another store | Track the other store's link under the **same name** |
| Stop watching something | On the page: **Remove** next to the item (✕ removes one store) |

## Is it working?
- **The Monday summary text arrived:** everything's fine.
- **No summary on Monday:** run `prices`, look at the "Last checked" dates, and open the log.
- **After a restart:** the checks and the page both come back on their own once you log in.
- **Going away:** keep the Mac plugged in. The 7:59 wake handles sleep. For power outages, turn on
  System Settings → Energy → **Start up automatically after a power failure**.

## Settings files
| File | What's in it | Edit it… |
|---|---|---|
| `.env` | Phone number (`ALERT_PHONE`), text label (`ALERT_LABEL`) | By hand, then `prices restart` |
| `PriceWatch/settings.json` | Summary and problem-alert choices | On the page |
| `PriceWatch/watchlist.json` | What you're tracking | On the page |

## Saving changes to GitHub
```
git add -A
git commit -m "what changed"
git push
```
