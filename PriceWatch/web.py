#!/usr/bin/env python3
"""PriceWatch web page: paste a product link, see what can be tracked, track it.

Uses only Python's built-in web server. Start it with ../start.sh, which opens
http://pricewatch.localhost:8503 (only reachable from this Mac).
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pricewatch as pw  # noqa: E402
from extract import fetch, size_status  # noqa: E402
from notify import send_text  # noqa: E402

PAGE = HERE / "ui.html"
# Logo files the page may load (a fixed list, so no other files can be requested)
ASSETS = {"/icon.png": ("assets/icon.png", "image/png"),
          "/favicon.ico": ("assets/icon.png", "image/png"),  # Safari asks for this on its own
          "/spodglabs.svg": ("assets/spodglabs.svg", "image/svg+xml")}


def probe(body: dict) -> dict:
    url = (body.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("That doesn't look like a link. Copy the product page's address from your browser.")
    res = fetch(url)
    if not res:
        return {"ok": False, "url": url, "store": pw.store_name(url)}
    sizes = [{"label": k, "price": v.get("price"), "available": v.get("available")}
             for k, v in res["sizes"].items()]
    return {"ok": True, "url": url, "store": pw.store_name(url), "title": res["title"],
            "price": res["price"], "currency": res["currency"], "available": res["in_stock"],
            "method": res["method"], "sizes": sizes,
            "names": [i["name"] for i in pw.load_list()["items"]]}


def add(body: dict) -> dict:
    target = body.get("target")
    return pw.add_url(body["url"], body["name"].strip(), (body.get("size") or "").strip() or None,
                      float(target) if target not in (None, "") else None)


def check(body: dict) -> dict:
    lines = []
    pw.run_check(dry_run=False, log=lines.append)
    return {"log": lines}


def schedule(body: dict) -> dict:
    every = body.get("every")
    msg = pw.install_schedule(int(every)) if every else pw.uninstall_schedule()
    return {"message": msg, "every": pw.schedule_status()}


POST = {
    "/api/probe": probe,
    "/api/add": add,
    "/api/remove": lambda b: {"removed": pw.remove_item(b["name"], b.get("url"))},
    "/api/search": lambda b: {"results": pw.search_shopify(b["store"], b["query"])},
    "/api/check": check,
    "/api/test-text": lambda b: {"sent": send_text("✅ Test message from your Mac"),
                                 "phone": bool(os.getenv("ALERT_PHONE"))},
    "/api/schedule": schedule,
    "/api/settings": lambda b: {"settings": pw.save_settings(b), "every": pw.schedule_status()},
}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def do_GET(self) -> None:
        u = urlparse(self.path)
        if u.path == "/":
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif u.path in ASSETS:
            path, ctype = ASSETS[u.path]
            self._send(200, (HERE / path).read_bytes(), ctype)
        elif u.path == "/api/items":
            self._json({"items": pw.watchlist_status(), "every": pw.schedule_status(),
                        "phone": bool(os.getenv("ALERT_PHONE")),
                        "settings": pw.load_settings()})
        elif u.path == "/api/history":
            self._json({"history": pw.history(parse_qs(u.query).get("name", [""])[0])})
        else:
            self._json({"error": "Not found"}, 404)

    def do_POST(self) -> None:
        fn = POST.get(urlparse(self.path).path)
        if not fn:
            return self._json({"error": "Not found"}, 404)
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            self._json(fn(body))
        except ValueError as e:
            self._json({"error": str(e)}, 400)
        except Exception as e:  # show the problem on the page instead of a dead button
            traceback.print_exc()
            self._json({"error": f"Something went wrong: {e}"}, 500)

    def log_message(self, fmt, *args) -> None:
        if "/api/" in (args[0] if args else ""):
            sys.stderr.write("%s\n" % (fmt % args))


def main() -> None:
    port = int(os.getenv("PORT", "8503"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"PriceWatch page at http://pricewatch.localhost:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
