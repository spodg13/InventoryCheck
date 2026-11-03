"""Read price / stock info from (almost) any product page.

Strategy, cheapest first:
  1. Shopify JSON  - any URL containing /products/<handle> is tried as <origin>/products/<handle>.js
  2. Plain HTTP    - fetch the HTML and read schema.org JSON-LD, OpenGraph/meta price tags, microdata
  3. Real browser  - same parsing, but on the page as rendered by headless Chromium (Nike, etc.)
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = 20


def _result(method: str, **kw) -> Dict[str, Any]:
    r = {"method": method, "title": None, "price": None, "currency": None,
         "in_stock": None, "sizes": {}}
    r.update(kw)
    return r


def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"\d[\d,]*\.?\d*", str(v))
    return float(m.group(0).replace(",", "")) if m else None


def _norm_size(s: str) -> str:
    return re.sub(r"[^a-z0-9.]", "", str(s).lower())


def size_matches(variant_label: str, wanted: str) -> bool:
    """'XL' matches 'XL', 'Men's XL', 'XL / Regular', 'M XL' but not 'XXL'."""
    w = _norm_size(wanted)
    parts = re.split(r"[\s/|,\-()]+", str(variant_label))
    return any(_norm_size(p) == w for p in parts if p) or _norm_size(variant_label) == w


# ---------------------------------------------------------------- Shopify
def try_shopify(url: str) -> Optional[Dict[str, Any]]:
    p = urlparse(url)
    m = re.search(r"/products/([^/?#]+)", p.path)
    if not m:
        return None
    api = f"{p.scheme}://{p.netloc}/products/{m.group(1)}.js"
    try:
        for attempt in range(2):  # Shopify rate-limits (429) now and then; wait and retry once
            r = requests.get(api, headers={"User-Agent": UA, "Accept": "*/*"}, timeout=TIMEOUT)
            if r.status_code != 429:
                break
            time.sleep(5)
        if r.status_code != 200:
            return None
        d = r.json()  # served as text/javascript, but the body is JSON
        if not isinstance(d, dict) or "variants" not in d:
            return None
    except (requests.RequestException, ValueError):
        return None
    sizes = {}
    prices = []
    for v in d.get("variants", []):
        sizes[v.get("title", "")] = {"available": bool(v.get("available")),
                                     "price": v.get("price", 0) / 100}
        prices.append(v.get("price", 0) / 100)
    return _result(
        "shopify", title=d.get("title"),
        price=min(prices) if prices else _to_float(d.get("price", 0)) / 100,
        currency=None, in_stock=bool(d.get("available")), sizes=sizes,
    )


# ---------------------------------------------------------------- HTML parsing
def _walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _types(node) -> List[str]:
    t = node.get("@type", [])
    return [str(x) for x in (t if isinstance(t, list) else [t])]


def _offer_info(offers) -> List[Dict[str, Any]]:
    out = []
    for o in offers if isinstance(offers, list) else [offers]:
        if not isinstance(o, dict):
            continue
        price = _to_float(o.get("price") or o.get("lowPrice"))
        if price is None and isinstance(o.get("priceSpecification"), dict):
            price = _to_float(o["priceSpecification"].get("price"))
        avail = o.get("availability")
        out.append({
            "price": price,
            "currency": o.get("priceCurrency"),
            "available": None if avail is None else "instock" in str(avail).lower().replace("_", ""),
            "label": " ".join(str(o.get(k, "")) for k in ("name", "sku") if o.get(k)),
        })
        if "offers" in o:  # AggregateOffer with nested offers
            out.extend(_offer_info(o["offers"]))
    return out


def parse_html(html: str, method: str) -> Optional[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    title = None
    offers: List[Dict[str, Any]] = []
    sizes: Dict[str, Dict[str, Any]] = {}

    # 1) JSON-LD
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except ValueError:
            continue
        for node in _walk(data):
            types = _types(node)
            if "Product" in types or "ProductGroup" in types:
                title = title or node.get("name")
                if "offers" in node:
                    o = _offer_info(node["offers"])
                    offers.extend(o)
                    if node.get("size") and o:
                        sizes[str(node["size"])] = {"available": o[0]["available"], "price": o[0]["price"]}
                for var in node.get("hasVariant", []) or []:
                    if isinstance(var, dict) and var.get("offers"):
                        vo = _offer_info(var["offers"])
                        if vo:
                            label = str(var.get("size") or var.get("name") or var.get("sku"))
                            sizes[label] = {"available": vo[0]["available"], "price": vo[0]["price"]}
                            offers.extend(vo)

    # 2) meta tags (OpenGraph / product:price)
    if not any(o["price"] for o in offers):
        meta_price = None
        currency = None
        for prop in ("product:price:amount", "og:price:amount", "twitter:data1"):
            t = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
            if t and _to_float(t.get("content")):
                meta_price = _to_float(t.get("content"))
                break
        for prop in ("product:price:currency", "og:price:currency"):
            t = soup.find("meta", attrs={"property": prop})
            if t:
                currency = t.get("content")
        # 3) microdata itemprop="price"
        if meta_price is None:
            t = soup.find(attrs={"itemprop": "price"})
            if t:
                meta_price = _to_float(t.get("content") or t.get_text())
        if meta_price is not None:
            offers.append({"price": meta_price, "currency": currency, "available": None, "label": ""})

    if not title:
        t = soup.find("meta", attrs={"property": "og:title"})
        title = t.get("content") if t else (soup.title.get_text(strip=True) if soup.title else None)

    priced = [o for o in offers if o["price"]]
    if not priced:
        return None
    for o in priced:  # offers named after a size (e.g. "Large", "XL") also count as sizes
        if o["label"] and o["label"] not in sizes:
            sizes[o["label"]] = {"available": o["available"], "price": o["price"]}
    avail = [o["available"] for o in priced if o["available"] is not None]
    return _result(
        method, title=title,
        price=min(o["price"] for o in priced),
        currency=next((o["currency"] for o in priced if o["currency"]), None),
        in_stock=any(avail) if avail else None,
        sizes=sizes,
    )


def try_http(url: str) -> Optional[Dict[str, Any]]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    return parse_html(r.text, "http")


def try_browser(url: str) -> Optional[Dict[str, Any]]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(user_agent=UA, viewport={"width": 1440, "height": 900},
                                      locale="en-US")
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass  # some sites never go idle; what we have is usually enough
            return parse_html(page.content(), "browser")
        except Exception:
            return None
        finally:
            browser.close()


METHODS = {"shopify": try_shopify, "http": try_http, "browser": try_browser}


def fetch(url: str, preferred: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Try the method that worked last time first, then the rest in cost order."""
    order = ["shopify", "http", "browser"]
    if preferred in order:
        order.remove(preferred)
        order.insert(0, preferred)
    for name in order:
        res = METHODS[name](url)
        if res and res.get("price"):
            return res
    return None


def size_status(res: Dict[str, Any], size: Optional[str]):
    """Return (available, price) for the wanted size, or the overall values if no size given/found."""
    if size:
        for label, info in res.get("sizes", {}).items():
            if size_matches(label, size):
                return info.get("available"), info.get("price") or res["price"]
    return res.get("in_stock"), res["price"]
