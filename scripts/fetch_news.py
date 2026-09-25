#!/usr/bin/env python3
"""Find the latest Jaffna / Northern Province / Sri Lanka news and read it in full.

Reads config/sources.json, keeps only stories from trusted publishers, sorts them into
categories and merges them into data/fetched.json. It then reads each new story's own
page so scripts/ai_enrich.py has the whole report to write our Tamil version from, and
finally rebuilds the site.

The article text this collects is working material only: it is cached in the gitignored
data/texts.json and is never published. What readers see is the Tamil rewrite.

Usage:
    python3 scripts/fetch_news.py            # fetch + rewrite + rebuild site
    python3 scripts/fetch_news.py --no-build # fetch only
    python3 scripts/fetch_news.py --no-text  # skip reading publishers' article pages
    python3 scripts/fetch_news.py -v         # verbose logging
"""
import argparse
import datetime as dt
import email.utils
import gzip
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
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "config" / "sources.json"
STORE_FILE = ROOT / "data" / "fetched.json"
# Article text is only working material for the Tamil rewrite; never published or committed.
TEXTS_FILE = ROOT / "data" / "texts.json"
LOG_FILE = ROOT / "logs" / "fetch.log"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
BROWSER_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/rss+xml;q=0.8,*/*;q=0.7",
    "Accept-Language": "ta,en-US;q=0.9,en;q=0.8",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "no-cache",
}

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


def decompress(body, encoding):
    """Some servers send gzip whatever the request asked for; urllib does not unpack it."""
    encoding = (encoding or "").lower()
    try:
        if "gzip" in encoding:
            return gzip.decompress(body)
        if "deflate" in encoding:
            return zlib.decompress(body, -zlib.MAX_WBITS)
    except Exception:
        return body
    if body[:2] == b"\x1f\x8b":  # gzip magic number, no matter what the header claimed
        try:
            return gzip.decompress(body)
        except Exception:
            pass
    return body


def http_get(url, timeout=20, retries=2):
    last_error = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=BROWSER_HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return decompress(resp.read(), resp.headers.get("Content-Encoding"))
        except Exception as e:  # network errors, HTTP errors, SSL errors
            last_error = e
            time.sleep(1.5 * (attempt + 1))
    # urllib can fail on some macOS Python installs (missing certificates); curl usually works.
    try:
        curl_headers = []
        for key, value in BROWSER_HEADERS.items():
            curl_headers += ["-H", "%s: %s" % (key, value)]
        out = subprocess.run(
            ["curl", "-sfL", "--compressed", "-m", str(timeout)] + curl_headers + [url],
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


def clean_title(title):
    """Normalise feed headlines and reject obvious fragments before storage."""
    title = re.sub(r"[\x00-\x1f\x7f]+", " ", title or "")
    title = re.sub(r"\s+", " ", title).strip()
    return re.sub(r"[\s\-–|:]+$", "", title)


def headline_is_fragment(title):
    compact = clean_title(title)
    letters = re.sub(r"[^\w\u0B80-\u0BFF]+", "", compact, flags=re.UNICODE)
    if len(letters) < 10 or len(compact.split()) < 2:
        return True
    last = re.sub(r"[^\w\u0B80-\u0BFF]+", "", compact.split()[-1], flags=re.UNICODE)
    return len(last) == 1


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


# ---------------------------------------------------------------- article pages

BOILERPLATE = ("விசேட செய்திகள்", "subscribe", "comments are disabled", "தவறவிடாதீர்கள்",
               "cookie", "newsletter", "all rights reserved", "follow us", "read more",
               "share this", "advertisement", "மேலும் படிக்க", "பிரதான செய்திகள்",
               "mirror ai summary", "generating summary")

# Blocks that never hold article prose.
CHROME_BLOCKS = r"(?is)<(script|style|nav|header|footer|aside|form|figure|noscript|iframe|svg)[^>]*>.*?</\1>"

# Containers that hold the article body, most specific first. Whichever yields the
# most prose wins, so the order only breaks ties.
BODY_CONTAINERS = (
    r'<div[^>]+itemprop=["\']articleBody["\'][^>]*>(.*)',
    r'<div[^>]+class=["\'][^"\']*(?:article-body|articleBody|entry-content|post-content|story-body|news-content|single-content|td-post-content)[^"\']*["\'][^>]*>(.*)',
    r'<article[^>]*>(.*?)</article>',
    r'<main[^>]*>(.*?)</main>',
)


def meta_content(page, name):
    for pattern in (r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]*content=["\']([^"\']*)',
                    r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']%s'):
        m = re.search(pattern % re.escape(name), page, re.I)
        if m:
            return html.unescape(m.group(1)).strip()
    return ""


def paragraphs_in(fragment):
    """Readable <p> paragraphs from a chunk of HTML, in document order."""
    found = []
    for raw in re.findall(r"(?is)<p[^>]*>(.*?)</p>", fragment):
        text = re.sub(r"<[^>]+>", " ", raw)
        text = re.sub(r"\s+", " ", html.unescape(text)).strip()
        lowered = text.lower()
        if len(text) >= 40 and text not in found and not any(b in lowered for b in BOILERPLATE):
            found.append(text)
    return found


def article_text(page, limit=8000):
    """The article's own prose, used as the input the Tamil rewrite is written from.

    Publishers wrap the story in different containers, so try each one and keep
    whichever yields the most paragraphs; fall back to the whole page when a site
    uses markup we do not recognise.
    """
    page = re.sub(CHROME_BLOCKS, " ", page)
    best = []
    for pattern in BODY_CONTAINERS:
        for fragment in re.findall(pattern, page, re.I | re.S):
            found = paragraphs_in(fragment)
            if len(" ".join(found)) > len(" ".join(best)):
                best = found
    if not best:
        best = paragraphs_in(page)
    text = "\n\n".join(best)
    return text[:limit]


def fetch_article(url, source, cfg):
    """Read one article page: headline, picture, opening text and published time."""
    page = http_get(url, timeout=cfg.get("request_timeout", 20)).decode("utf-8", "replace")
    title = meta_content(page, "og:title") or strip_html(re.search(r"(?is)<title[^>]*>(.*?)</title>", page).group(1)
                                                          if re.search(r"(?is)<title", page) else "")
    strip_suffix = source.get("title_strip")
    if strip_suffix and title.endswith(strip_suffix):
        title = title[: -len(strip_suffix)].strip()
    published = None
    if source.get("date_regex"):
        m = re.search(source["date_regex"], page)
        if m:
            try:
                naive = dt.datetime.strptime(m.group(1), source["date_format"])
                published = naive.replace(tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
            except ValueError:
                published = None
    return {
        "title": clean_title(strip_html(title)),
        "link": url,
        "image": meta_content(page, "og:image") or None,
        "text": article_text(page),
        "published": published.astimezone(dt.timezone.utc) if published else None,
    }


def collect_html_index(source, cfg, now, known_links):
    """Read a news site's front page, then each new article page behind it."""
    index = http_get(source["url"], timeout=cfg.get("request_timeout", 20)).decode("utf-8", "replace")
    links, seen = [], set()
    for link in re.findall(source["link_pattern"], index):
        if link not in seen:
            seen.add(link)
            links.append(link)
    fresh = [l for l in links if l not in known_links][: source.get("max_items", 8)]
    max_age = dt.timedelta(days=cfg.get("max_age_days", 7))
    results, texts = [], {}
    for n, link in enumerate(fresh):
        if n:
            time.sleep(source.get("delay_seconds", 5))  # be polite to the publisher
        try:
            art = fetch_article(link, source, cfg)
        except Exception as e:
            log.debug("  article failed %s: %s", link, e)
            continue
        if not art["title"] or headline_is_fragment(art["title"]):
            continue
        published = art["published"] or now
        if now - published > max_age:
            continue
        body = art["text"]
        for junk in (art["title"] + (source.get("title_strip") or ""), art["title"]):
            body = body.replace(junk, " ")
        body = re.sub(r"\s+", " ", body).strip()
        summary = shorten(body, cfg.get("excerpt_chars", 300))
        category, tags = categorise(art["title"] + " " + summary, source.get("default_category"), cfg)
        item_id = make_id(link)
        results.append({
            "id": item_id, "type": "auto", "title": art["title"], "summary": summary, "link": link,
            "source": source.get("source_name") or source["name"], "source_domain": domain_of(link),
            "image": art["image"], "lang": source.get("lang", "ta"), "category": category, "tags": tags,
            "published": published.isoformat(), "fetched": now.isoformat(),
        })
        texts[item_id] = body
    log.info("%-38s %3d kept  (%d links on page)", source["name"], len(results), len(links))
    return results, texts


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
    results, texts = [], {}
    skipped_untrusted = 0

    for e in entries:
        if not e["title"] or not e["link"]:
            continue
        published = e["published"] or now
        if now - published > max_age or published - now > dt.timedelta(hours=6):
            continue

        title = clean_title(e["title"])
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
            summary = shorten(clean_summary(strip_html(e["description"]), title), cfg.get("excerpt_chars", 300))

        if not is_trusted(domain, trusted):
            skipped_untrusted += 1
            continue
        publisher = publisher_name(domain, cfg) or publisher or domain
        title = clean_title(title)
        if headline_is_fragment(title):
            continue

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
        texts[results[-1]["id"]] = summary
        if len(results) >= source.get("max_items", 20):
            break

    log.info("%-38s %3d kept  (%d entries, %d untrusted skipped)",
             source["name"], len(results), len(entries), skipped_untrusted)
    return results, texts


# ---------------------------------------------------------------- full article text

def fetchable(link):
    """A link we can actually read. Google News hands out an opaque redirect that
    resolves only through its own internal endpoint, so those stories can never be
    more than a bare headline."""
    return domain_of(link) != "news.google.com"


def needs_rewrite(item):
    """Stories we have not yet rewritten in our own Tamil."""
    return item.get("type") != "local" and not item.get("ai_body")


def fill_article_texts(items, texts, cfg, now):
    """Read each unwritten story's own page, so the Tamil rewrite works from the
    whole report rather than the one-line teaser a feed syndicates.

    Only stories still waiting to be rewritten are fetched, which keeps a routine
    run to the handful of headlines that arrived since the last one.
    """
    min_chars = cfg.get("min_text_chars", 400)
    budget = cfg.get("max_article_fetches", 60)
    # Polite crawl delays mean this step could otherwise outlast the half-hourly
    # schedule; whatever it does not reach is picked up by the next run.
    deadline = time.time() + cfg.get("max_article_seconds", 420)
    delays = cfg.get("article_delay_seconds", {})
    default_delay = cfg.get("default_article_delay", 2)
    last_seen = {}
    fetched = filled = 0

    for item in items:
        if fetched >= budget or time.time() > deadline:
            break
        if not needs_rewrite(item) or len(texts.get(item["id"], "")) >= min_chars:
            continue
        if not fetchable(item["link"]):
            continue
        domain = item.get("source_domain") or domain_of(item["link"])
        delay = delays.get(domain, default_delay)
        waited = time.time() - last_seen.get(domain, 0)
        if waited < delay:
            time.sleep(delay - waited)
        last_seen[domain] = time.time()
        fetched += 1
        try:
            page = http_get(item["link"], timeout=cfg.get("request_timeout", 20), retries=1)
        except Exception as e:
            log.debug("  page failed %s: %s", item["link"], e)
            continue
        page = page.decode("utf-8", "replace")
        text = article_text(page)
        # The feed teaser is usually the article's own first line; keep whichever is fuller.
        if len(text) < len(texts.get(item["id"], "")):
            text = texts[item["id"]]
        if len(text) >= min_chars:
            texts[item["id"]] = text
            filled += 1
        elif text:
            texts[item["id"]] = text
        if not item.get("image"):
            item["image"] = meta_content(page, "og:image") or None

    log.info("Article pages read: %d fetched, %d now have enough text to rewrite", fetched, filled)
    return filled


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
    items = [i for i in by_id.values()
             if now - parse_date(i["published"]) <= max_age and fetchable(i["link"])]
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
    parser.add_argument("--no-ai", action="store_true", help="skip the Tamil rewrite / translation step")
    parser.add_argument("--no-text", action="store_true", help="do not read publishers' article pages")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose)

    cfg = load_json(SOURCES_FILE, None)
    if cfg is None:
        log.error("Missing %s", SOURCES_FILE)
        return 1

    now = dt.datetime.now(dt.timezone.utc)
    log.info("Fetching news (%s)", now.strftime("%Y-%m-%d %H:%M UTC"))
    store = load_json(STORE_FILE, {"items": []})
    texts = load_json(TEXTS_FILE, {})
    known_links = {i["link"] for i in store.get("items", [])}

    new_items, failures = [], 0
    for source in cfg.get("sources", []):
        if not source.get("enabled", True):
            continue
        try:
            if source.get("type") == "html_index":
                found, found_texts = collect_html_index(source, cfg, now, known_links)
            else:
                found, found_texts = collect(source, cfg, now)
            new_items.extend(found)
            # A feed teaser must not displace the full article text a previous run read.
            for key, value in found_texts.items():
                if len(value) > len(texts.get(key, "")):
                    texts[key] = value
        except Exception as e:
            failures += 1
            log.warning("%-38s FAILED: %s", source.get("name"), e)

    items, added = merge(store.get("items", []), new_items, cfg, now)
    log.info("Added %d new items, %d stored in total, %d source(s) failed", added, len(items), failures)

    if not args.no_text:
        fill_article_texts(items, texts, cfg, now)

    save_json(STORE_FILE, {"updated": now.isoformat(), "items": items})
    live = {i["id"] for i in items}
    save_json(TEXTS_FILE, {k: v for k, v in texts.items() if k in live})

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    if not args.no_ai:
        # The Anthropic SDK needs Python 3.10+, so use the project venv when the
        # interpreter running this script is older.
        venv_python = ROOT / ".venv" / "bin" / "python"
        python = str(venv_python) if venv_python.exists() else sys.executable
        try:
            out = subprocess.run([python, str(ROOT / "scripts" / "ai_enrich.py"), "--no-build"],
                                 capture_output=True, text=True, timeout=1800)
            for line in (out.stdout + out.stderr).strip().splitlines():
                log.info("%s", line)
        except Exception as e:
            log.warning("AI summaries skipped: %s", e)

    if not args.no_build:
        import build
        build.build()

    # Fail only when every source failed, so schedulers can alert on it.
    enabled = [s for s in cfg.get("sources", []) if s.get("enabled", True)]
    return 1 if enabled and failures == len(enabled) else 0


if __name__ == "__main__":
    sys.exit(main())
