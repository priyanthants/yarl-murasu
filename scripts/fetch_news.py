#!/usr/bin/env python3
"""Fetch the latest Jaffna / Northern Province / Sri Lanka news from trusted sources.

Reads config/sources.json, keeps only items from trusted publishers, sorts them
into categories, merges them into data/fetched.json and then rebuilds the site.

Only the headline, a short summary and a link back to the original publisher are
stored; full articles are never copied.

Usage:
    python3 scripts/fetch_news.py            # fetch + rebuild site
    python3 scripts/fetch_news.py --no-build # fetch only
    python3 scripts/fetch_news.py -v         # verbose logging
"""
import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import logging
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "config" / "sources.json"
STORE_FILE = ROOT / "data" / "fetched.json"
LOG_FILE = ROOT / "logs" / "fetch.log"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
NS = {
    "media": "http://search.yahoo.com/mrss/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "atom": "http://www.w3.org/2005/Atom",
}
SUMMARY_LIMIT = 320

log = logging.getLogger("fetch")


# ---------------------------------------------------------------- helpers

def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    tmp.replace(path)


def http_get(url, timeout=20, retries=2):
    last_error = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as e:  # network errors, HTTP errors, SSL errors
            last_error = e
            time.sleep(1.5 * (attempt + 1))
    # urllib can fail on some macOS Python installs (missing certificates); curl usually works.
    try:
        out = subprocess.run(
            ["curl", "-sfL", "-m", str(timeout), "-A", USER_AGENT, url],
            capture_output=True, check=True,
        )
        return out.stdout
    except Exception:
        raise last_error


def strip_html(text):
    if not text:
        return ""
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def shorten(text, limit=SUMMARY_LIMIT):
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,.;:-") + "…"


def parse_date(value):
    if not value:
        return None
    value = value.strip()
    try:
        d = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        d = None
    if d is None:
        try:
            d = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def domain_of(url):
    host = urllib.parse.urlparse(url or "").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def is_trusted(domain, trusted):
    return any(domain == d or domain.endswith("." + d) for d in trusted)


def publisher_name(domain, cfg):
    names = cfg.get("publisher_names", {})
    for d in sorted(names, key=len, reverse=True):  # most specific domain first
        if domain == d or domain.endswith("." + d):
            return names[d]
    return ""


def clean_summary(summary, title):
    """Drop a repeated headline and byline/date boilerplate that some feeds put first."""
    if summary.startswith(title):
        summary = summary[len(title):].lstrip(" -–:|")
    summary = re.sub(r"^by .{1,60}?\d{1,2}/\d{1,2}/\d{4}\s*-\s*\d{1,2}:\d{2}\s*(Body\s*)?", "", summary)
    return summary.strip()


def title_key(title):
    """Normalised title used to spot the same story from several outlets."""
    t = re.sub(r"[\W_]+", "", title.lower())
    return t[:60]


def make_id(link):
    return hashlib.sha1(link.encode("utf-8")).hexdigest()[:12]


def child_text(el, path):
    found = el.find(path, NS)
    if found is None:
        return ""
    return "".join(found.itertext()).strip()


# ---------------------------------------------------------------- parsing

def parse_xml(raw):
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        # Feeds sometimes contain HTML entities such as &nbsp; that are not valid XML.
        fixed = re.sub(rb"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", b"&amp;", raw)
        return ET.fromstring(fixed)


def find_image(item, description_html):
    for tag in ("media:thumbnail", "media:content"):
        for el in item.findall(tag, NS):
            url = el.get("url")
            medium = el.get("medium", "")
            mime = el.get("type", "")
            if url and (tag == "media:thumbnail" or medium == "image" or mime.startswith("image") or not mime):
                return url
    for el in item.findall("media:group/media:content", NS):
        if el.get("url"):
            return el.get("url")
    enc = item.find("enclosure")
    if enc is not None and enc.get("type", "").startswith("image") and enc.get("url"):
        return enc.get("url")
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', description_html or "", re.I)
    if m and not m.group(1).startswith("data:"):
        return html.unescape(m.group(1))
    return None


def parse_feed(raw):
    """Return a list of raw entries from an RSS or Atom document."""
    root = parse_xml(raw)
    entries = []
    if root.tag.endswith("feed"):  # Atom
        for e in root.findall("atom:entry", NS):
            link = ""
            for l in e.findall("atom:link", NS):
                if l.get("rel", "alternate") == "alternate":
                    link = l.get("href", "")
                    break
            desc = child_text(e, "atom:summary") or child_text(e, "atom:content")
            entries.append({
                "title": strip_html(child_text(e, "atom:title")),
                "link": link,
                "description": desc,
                "published": parse_date(child_text(e, "atom:published") or child_text(e, "atom:updated")),
                "image": find_image(e, desc),
                "source_name": "",
                "source_url": "",
            })
        return entries

    for it in root.iter("item"):
        desc = it.findtext("description") or ""
        encoded = child_text(it, "content:encoded")
        src = it.find("source")
        entries.append({
            "title": strip_html(it.findtext("title") or ""),
            "link": (it.findtext("link") or "").strip(),
            "description": desc or encoded,
            "published": parse_date(it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date")),
            "image": find_image(it, desc + encoded),
            "source_name": (src.text or "").strip() if src is not None else "",
            "source_url": src.get("url", "") if src is not None else "",
        })
    return entries


# ---------------------------------------------------------------- categorising

def categorise(text, default, cfg):
    keywords = cfg.get("category_keywords", {})
    tags = []
    lowered = text.lower()
    for cat in cfg.get("category_priority", list(keywords)):
        if any(k.lower() in lowered for k in keywords.get(cat, [])):
            tags.append(cat)
    if default and default not in tags:
        tags.append(default)
    primary = tags[0] if tags else (default or "srilanka")
    return primary, tags


# ---------------------------------------------------------------- sources

def google_news_url(source):
    params = {
        "q": source["query"],
        "hl": source.get("hl", "ta"),
        "gl": source.get("gl", "LK"),
        "ceid": source.get("ceid", "LK:ta"),
    }
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)


def collect(source, cfg, now):
    kind = source.get("type", "rss")
    url = google_news_url(source) if kind == "google_news" else source["url"]
    raw = http_get(url, timeout=cfg.get("request_timeout", 20))
    entries = parse_feed(raw)

    trusted = cfg.get("trusted_domains", [])
    max_age = dt.timedelta(days=cfg.get("max_age_days", 10))
    required = [k.lower() for k in source.get("require_keywords", [])]
    results = []
    skipped_untrusted = 0

    for e in entries:
        if not e["title"] or not e["link"]:
            continue
        published = e["published"] or now
        if now - published > max_age or published - now > dt.timedelta(hours=6):
            continue

        title = e["title"]
        if kind == "google_news":
            publisher = e["source_name"]
            domain = domain_of(e["source_url"])
            # Google appends " - Publisher" to every headline.
            if publisher and title.endswith(" - " + publisher):
                title = title[: -len(publisher) - 3].strip()
            summary = ""  # Google's description is only a link list
        else:
            publisher = source.get("source_name") or source["name"]
            domain = domain_of(e["link"])
            summary = shorten(clean_summary(strip_html(e["description"]), title))

        if not is_trusted(domain, trusted):
            skipped_untrusted += 1
            continue
        publisher = publisher_name(domain, cfg) or publisher or domain
        title = re.sub(r"[\s\-–|:]+$", "", title)

        text = title + " " + summary
        if required and not any(k in text.lower() for k in required):
            continue

        category, tags = categorise(text, source.get("default_category"), cfg)
        results.append({
            "id": make_id(e["link"]),
            "type": "auto",
            "title": title,
            "summary": summary,
            "link": e["link"],
            "source": publisher,
            "source_domain": domain,
            "image": e["image"],
            "lang": source.get("lang", "ta"),
            "category": category,
            "tags": tags,
            "published": published.isoformat(),
            "fetched": now.isoformat(),
        })
        if len(results) >= source.get("max_items", 20):
            break

    log.info("%-32s %3d kept  (%d entries, %d untrusted skipped)",
             source["name"], len(results), len(entries), skipped_untrusted)
    return results


def merge(existing, new_items, cfg, now):
    by_id = {i["id"]: i for i in existing}
    seen_titles = {title_key(i["title"]) for i in existing}
    added = 0
    for item in new_items:
        key = title_key(item["title"])
        if item["id"] in by_id:
            old = by_id[item["id"]]
            old["source"] = item["source"]
            old["summary"] = item["summary"]
            if not old.get("image") and item.get("image"):
                old["image"] = item["image"]
            continue
        if key in seen_titles:
            continue
        by_id[item["id"]] = item
        seen_titles.add(key)
        added += 1

    max_age = dt.timedelta(days=cfg.get("max_age_days", 10))
    items = [i for i in by_id.values() if now - parse_date(i["published"]) <= max_age]
    items.sort(key=lambda i: i["published"], reverse=True)
    return items[: cfg.get("max_store_items", 400)], added


# ---------------------------------------------------------------- main

def setup_logging(verbose):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(fh)
    log.addHandler(sh)
    log.setLevel(logging.DEBUG if verbose else logging.INFO)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-build", action="store_true", help="do not rebuild the site afterwards")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose)

    cfg = load_json(SOURCES_FILE, None)
    if cfg is None:
        log.error("Missing %s", SOURCES_FILE)
        return 1

    now = dt.datetime.now(dt.timezone.utc)
    log.info("Fetching news (%s)", now.strftime("%Y-%m-%d %H:%M UTC"))
    new_items, failures = [], 0
    for source in cfg.get("sources", []):
        if not source.get("enabled", True):
            continue
        try:
            new_items.extend(collect(source, cfg, now))
        except Exception as e:
            failures += 1
            log.warning("%-32s FAILED: %s", source.get("name"), e)

    store = load_json(STORE_FILE, {"items": []})
    items, added = merge(store.get("items", []), new_items, cfg, now)
    save_json(STORE_FILE, {"updated": now.isoformat(), "items": items})
    log.info("Added %d new items, %d stored in total, %d source(s) failed", added, len(items), failures)

    if not args.no_build:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import build
        build.build()

    # Fail only when every source failed, so schedulers can alert on it.
    enabled = [s for s in cfg.get("sources", []) if s.get("enabled", True)]
    return 1 if enabled and failures == len(enabled) else 0


if __name__ == "__main__":
    sys.exit(main())
