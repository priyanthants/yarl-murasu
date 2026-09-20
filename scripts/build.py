#!/usr/bin/env python3
"""Build the static website in site/.

Combines your own posts (content/posts.json) with fetched news
(data/fetched.json), then writes:
    site/index.html          home page (rendered in the browser from data/news.js)
    site/news/<id>.html      one page per story, with Facebook/X preview tags
    site/data/news.js        data used by the home page, ads and ticker
    site/sitemap.xml, site/rss.xml   when site_url is set in config/site.json

Usage:
    python3 scripts/build.py
"""
import datetime as dt
import html
import json
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
TEMPLATES = ROOT / "templates"
NEWS_DIR = SITE / "news"

SL_TZ = dt.timezone(dt.timedelta(hours=5, minutes=30), "IST")
TA_MONTHS = ["ஜனவரி", "பெப்ரவரி", "மார்ச்", "ஏப்ரல்", "மே", "ஜூன்", "ஜூலை",
             "ஓகஸ்ட்", "செப்டெம்பர்", "ஒக்டோபர்", "நவம்பர்", "டிசம்பர்"]
TA_WEEKDAYS = ["திங்கள்", "செவ்வாய்", "புதன்", "வியாழன்", "வெள்ளி", "சனி", "ஞாயிறு"]

esc = html.escape


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def render(template, ctx):
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(ctx.get(m.group(1), "")), template)


def parse_date(value):
    try:
        d = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return dt.datetime.now(dt.timezone.utc)
    if d.tzinfo is None:
        d = d.replace(tzinfo=SL_TZ)
    return d


def tamil_date(d, with_time=True):
    d = d.astimezone(SL_TZ)
    text = "%s, %d %s %d" % (TA_WEEKDAYS[d.weekday()], d.day, TA_MONTHS[d.month - 1], d.year)
    if with_time:
        period = "முற்பகல்" if d.hour < 12 else "பிற்பகல்"
        hour = d.hour % 12 or 12
        text += " · %s %d:%02d" % (period, hour, d.minute)
    return text


def asset(path, base):
    """Resolve a site-relative path (uploads/x.jpg) for a page living at `base`."""
    if not path:
        return ""
    if re.match(r"^(https?:)?//|^data:", path):
        return path
    return base + path.lstrip("/")


# ---------------------------------------------------------------- video links

def video_embed_url(url):
    """Turn a YouTube / Facebook / Vimeo / Instagram / TikTok link into an embeddable URL."""
    u = url.strip()
    m = re.search(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/)|youtu\.be/)([\w-]{11})", u)
    if m:
        return "https://www.youtube-nocookie.com/embed/" + m.group(1), "youtube", m.group(1)
    m = re.search(r"vimeo\.com/(?:video/)?(\d+)", u)
    if m:
        return "https://player.vimeo.com/video/" + m.group(1), "vimeo", m.group(1)
    if re.search(r"(facebook\.com|fb\.watch)/", u):
        return ("https://www.facebook.com/plugins/video.php?show_text=false&href="
                + urllib.parse.quote(u, safe="")), "facebook", None
    m = re.search(r"instagram\.com/(?:p|reel|tv)/([\w-]+)", u)
    if m:
        return "https://www.instagram.com/p/%s/embed" % m.group(1), "instagram", m.group(1)
    m = re.search(r"tiktok\.com/.*/video/(\d+)", u)
    if m:
        return "https://www.tiktok.com/embed/v2/" + m.group(1), "tiktok", m.group(1)
    if re.search(r"\.(mp4|webm|ogg)(\?|$)", u, re.I):
        return u, "file", None
    return None, "link", None


def video_html(url, base):
    embed, kind, _ = video_embed_url(url)
    if kind == "file":
        return '<div class="video-frame"><video controls preload="metadata" src="%s"></video></div>' % esc(asset(url, base))
    if embed:
        ratio = " tall" if kind in ("instagram", "tiktok") or "/shorts/" in url else ""
        return ('<div class="video-frame%s"><iframe src="%s" title="காணொளி" loading="lazy" '
                'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" '
                'allowfullscreen></iframe></div>' % (ratio, esc(embed)))
    return ('<a class="btn btn-outline" href="%s" target="_blank" rel="noopener">'
            '<svg class="i"><use href="#i-play"/></svg> காணொளியைப் பார்க்க</a>' % esc(url))


# ---------------------------------------------------------------- items

def normalise_post(p, site):
    """Own posts from content/posts.json."""
    item = dict(p)
    item["type"] = "local"
    item.setdefault("source", site["name"])
    item.setdefault("images", [])
    item.setdefault("videos", [])
    item.setdefault("tags", [item.get("category", "jaffna")])
    item["image"] = item.get("image") or (item["images"][0] if item["images"] else None)
    item["published"] = parse_date(item.get("published")).isoformat()
    return item


def collect_items(site):
    posts = load_json(ROOT / "content" / "posts.json", [])
    fetched = load_json(ROOT / "data" / "fetched.json", {"items": []}).get("items", [])
    now = dt.datetime.now(dt.timezone.utc)
    items = [normalise_post(p, site) for p in posts
             if not p.get("draft") and parse_date(p.get("published")) <= now + dt.timedelta(minutes=5)]
    items += fetched
    seen, unique = set(), []
    for i in items:
        if i["id"] not in seen:
            seen.add(i["id"])
            unique.append(i)
    unique.sort(key=lambda i: parse_date(i["published"]), reverse=True)
    return unique[: site.get("max_items", 200)]


def display(i):
    """What the reader sees: Tamil headline and our own Tamil summary when we have them."""
    out = dict(i)
    if i.get("title_ta"):
        out["title"] = i["title_ta"]
        out["orig_title"] = i["title"]
    if i.get("ai_summary"):
        out["summary"] = i["ai_summary"]
        out["ai"] = True
        out["excerpt"] = i.get("summary", "")
    return out


def client_item(i):
    """The subset of fields the browser needs."""
    i = display(i)
    keep = ("id", "type", "title", "summary", "source", "image", "category", "tags",
            "published", "lang", "link", "images", "videos", "breaking", "featured", "ai")
    out = {k: i[k] for k in keep if i.get(k) not in (None, "", [], False)}
    if i.get("type") == "local" and i.get("body") and not i.get("summary"):
        out["summary"] = i["body"][:220].rsplit(" ", 1)[0] + "…" if len(i["body"]) > 220 else i["body"]
    return out


# ---------------------------------------------------------------- page parts

def nav_items(site, base):
    return "\n".join(
        '<li><a href="%sindex.html#cat=%s" data-cat="%s">%s</a></li>' % (base, c["id"], c["id"], esc(c["name"]))
        for c in site["categories"])


def social_links(site):
    labels = {"facebook": ("fb", "Facebook"), "instagram": ("ig", "Instagram"), "x": ("x", "X"),
              "youtube": ("yt", "YouTube"), "whatsapp": ("wa", "WhatsApp")}
    out = []
    for key, (icon, label) in labels.items():
        url = site.get("social", {}).get(key)
        if url:
            out.append('<a class="social s-%s" href="%s" target="_blank" rel="noopener" aria-label="%s">'
                       '<svg class="i"><use href="#i-%s"/></svg></a>' % (icon, esc(url), label, icon))
    return "".join(out)


def share_bar(extra_class=""):
    return """<div class="share-bar %s">
  <span class="share-label">பகிர்க</span>
  <button class="sh sh-fb" data-net="facebook" aria-label="Facebook இல் பகிர்க"><svg class="i"><use href="#i-fb"/></svg><span>Facebook</span></button>
  <button class="sh sh-x" data-net="x" aria-label="X இல் பகிர்க"><svg class="i"><use href="#i-x"/></svg></button>
  <button class="sh sh-ig" data-net="instagram" aria-label="Instagram இல் பகிர்க"><svg class="i"><use href="#i-ig"/></svg><span>Instagram</span></button>
  <button class="sh sh-wa" data-net="whatsapp" aria-label="WhatsApp இல் பகிர்க"><svg class="i"><use href="#i-wa"/></svg><span>WhatsApp</span></button>
  <button class="sh sh-copy" data-net="copy" aria-label="இணைப்பை நகலெடு"><svg class="i"><use href="#i-link"/></svg></button>
</div>""" % extra_class


def paragraphs(text):
    parts = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    return "\n".join("<p>%s</p>" % esc(p).replace("\n", "<br>") for p in parts)


def placeholder_html(item, cats):
    cat = cats.get(item.get("category"), {"name": "", "color": "#8b1e1e"})
    return ('<div class="ph" style="--c:%s"><span class="ph-cat">%s</span><span class="ph-src">%s</span></div>'
            % (cat["color"], esc(cat["name"]), esc(item.get("source", ""))))


def article_page(item, ctx_base, site, cats, related):
    base = "../"
    cat = cats.get(item.get("category"), {"id": "srilanka", "name": "செய்தி", "color": "#8b1e1e"})
    is_local = item.get("type") == "local"
    published = parse_date(item["published"])
    images = [asset(p, base) for p in item.get("images", [])] if is_local else []
    hero_img = images[0] if images else asset(item.get("image") or "", base)

    if hero_img:
        hero = ('<figure class="article-hero"><img src="%s" alt="%s" data-lightbox="0">%s</figure>'
                % (esc(hero_img), esc(item["title"]),
                   '<figcaption>%s</figcaption>' % esc(item["caption"]) if item.get("caption") else ""))
    elif item.get("videos"):
        hero = ""
    else:
        hero = '<div class="article-hero">%s</div>' % placeholder_html(item, cats)

    gallery = ""
    if len(images) > 1:
        gallery = ('<section class="gallery"><h2 class="block-title">புகைப்படங்கள்</h2><div class="gallery-grid">%s</div></section>'
                   % "".join('<button class="gallery-item" data-lightbox="%d"><img src="%s" alt="" loading="lazy"></button>'
                             % (n, esc(src)) for n, src in enumerate(images)))
    videos = ""
    if item.get("videos"):
        videos = ('<section class="videos"><h2 class="block-title">காணொளிகள்</h2>%s</section>'
                  % "".join(video_html(v, base) for v in item["videos"]))

    if is_local:
        body = paragraphs(item.get("body") or item.get("summary", ""))
        summary = '<p class="lede">%s</p>' % esc(item["summary"]) if item.get("summary") and item.get("body") else ""
        source_box = ""
        byline = esc(item.get("author") or site["name"])
    else:
        summary = ""
        parts = []
        if item.get("summary"):
            parts.append('<p class="lede">%s</p>' % esc(item["summary"]))
            if item.get("ai"):
                parts.append('<p class="ai-note">இந்தச் சுருக்கம், %s வெளியிட்ட செய்தியின் அடிப்படையில் '
                             'தானியங்கி உதவியுடன் தமிழில் தயாரிக்கப்பட்டது.</p>' % esc(item.get("source", "")))
            if item.get("excerpt") and item["excerpt"] != item["summary"]:
                parts.append('<blockquote class="source-quote"><p>%s</p><cite>— %s</cite></blockquote>'
                             % (esc(item["excerpt"]), esc(item.get("source", ""))))
        else:
            parts.append('<p class="thin-note">இது தலைப்புச் செய்தி மட்டும். முழு விவரங்களை மூலத்தில் வாசிக்கலாம்.</p>')
        if item.get("orig_title"):
            parts.append('<p class="orig-title">மூலத் தலைப்பு (English): %s</p>' % esc(item["orig_title"]))
        body = "\n".join(parts)
        source_box = """<div class="source-box">
  <div><span class="source-box-label">மூலம்</span><strong>%s</strong>
  <p>இந்தச் செய்தி %s இணையத்தளத்தில் வெளியானது. முழு விவரங்களையும் அங்கே வாசிக்கலாம்.</p></div>
  <a class="btn" href="%s" target="_blank" rel="noopener">முழுச் செய்தியை வாசிக்க <svg class="i"><use href="#i-ext"/></svg></a>
</div>""" % (esc(item.get("source", "")), esc(item.get("source", "")), esc(item["link"]))
        byline = esc(item.get("source", ""))

    lang_badge = '<span class="lang-badge">English</span>' if item.get("lang") == "en" else ""
    related_html = "".join(
        '<li><a href="%s.html"><span class="rel-title">%s</span><span class="rel-meta">%s</span></a></li>'
        % (esc(r["id"]), esc(r["title"]), esc(r.get("source", ""))) for r in related)

    description = item.get("summary") or item.get("body", "")[:200] or item["title"]
    site_url = site.get("site_url", "").rstrip("/")
    page_url = "%s/news/%s.html" % (site_url, item["id"]) if site_url else ""
    og_image = hero_img
    if og_image and not og_image.startswith("http") and site_url:
        og_image = site_url + "/" + og_image.replace("../", "", 1)

    return {
        "id": esc(item["id"]),
        "title": esc(item["title"]),
        "description": esc(description[:200]),
        "page_url": esc(page_url),
        "og_image": esc(og_image) if og_image.startswith("http") else "",
        "cat_id": cat.get("id", item.get("category")),
        "cat_name": esc(cat["name"]),
        "cat_color": cat["color"],
        "iso": published.isoformat(),
        "date_human": tamil_date(published),
        "byline": byline,
        "lang_badge": lang_badge,
        "hero": hero,
        "summary": summary,
        "body": body,
        "gallery": gallery,
        "videos": videos,
        "source_box": source_box,
        "share_top": share_bar(),
        "share_bottom": share_bar("share-bottom"),
        "related": related_html,
        "images_json": esc(json.dumps(images or ([hero_img] if hero_img else []), ensure_ascii=False)),
    }


def rss_xml(site, items):
    url = site["site_url"].rstrip("/")
    entries = []
    for i in items[:50]:
        i = display(i)
        entries.append("<item><title>%s</title><link>%s/news/%s.html</link><guid>%s/news/%s.html</guid>"
                       "<pubDate>%s</pubDate><description>%s</description></item>" % (
                           esc(i["title"]), url, i["id"], url, i["id"],
                           parse_date(i["published"]).strftime("%a, %d %b %Y %H:%M:%S %z"),
                           esc(i.get("summary", ""))))
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><title>%s</title><link>%s/</link>'
            '<description>%s</description><language>ta</language>%s</channel></rss>\n'
            % (esc(site["name"]), url, esc(site.get("description", "")), "".join(entries)))


def sitemap_xml(site, items):
    url = site["site_url"].rstrip("/")
    locs = ["<url><loc>%s/</loc></url>" % url]
    locs += ["<url><loc>%s/news/%s.html</loc><lastmod>%s</lastmod></url>"
             % (url, i["id"], parse_date(i["published"]).date().isoformat()) for i in items]
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</urlset>\n'
            % "".join(locs))


# ---------------------------------------------------------------- build

def build(verbose=True):
    site = load_json(ROOT / "config" / "site.json", None)
    ads = load_json(ROOT / "config" / "ads.json", {"slots": {}})
    ads.pop("_help", None)
    cats = {c["id"]: c for c in site["categories"]}
    items = collect_items(site)
    version = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")

    partial = {name: (TEMPLATES / ("_%s.html" % name)).read_text(encoding="utf-8")
               for name in ("head", "header", "footer")}

    def page_ctx(base, extra):
        ctx = {
            "base": base,
            "v": version,
            "site_name": esc(site["name"]),
            "site_name_en": esc(site.get("name_en", "")),
            "tagline": esc(site.get("tagline", "")),
            "site_description": esc(site.get("description", "")),
            "nav_items": nav_items(site, base),
            "social_links": social_links(site),
            "year": dt.datetime.now(SL_TZ).year,
            "contact": ('<a href="mailto:%s">%s</a>' % (esc(site["contact_email"]), esc(site["contact_email"]))
                        if site.get("contact_email") else ""),
        }
        ctx.update(extra)
        for name, tpl in partial.items():
            ctx[name] = render(tpl, ctx)
        return ctx

    # data file used by every page
    public_site = {k: site.get(k) for k in ("name", "name_en", "tagline", "site_url", "social", "categories",
                                              "home_page_size", "in_feed_ad_every", "breaking_hours")}
    data = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(), "site": public_site, "ads": ads,
            "items": [client_item(i) for i in items]}
    write(SITE / "data" / "news.js",
          "window.NEWS_DATA = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n")

    # home page
    index_tpl = (TEMPLATES / "index.html").read_text(encoding="utf-8")
    write(SITE / "index.html", render(index_tpl, page_ctx("", {
        "page_title": esc(site["name"]) + " — " + esc(site.get("tagline", "")),
        "page_description": esc(site.get("description", "")),
        "page_url": esc(site.get("site_url", "")),
        "og_image": "",
        "og_type": "website",
    })))

    # story pages
    article_tpl = (TEMPLATES / "article.html").read_text(encoding="utf-8")
    wanted = set()
    for item in (display(i) for i in items):
        related = [display(r) for r in items if r["id"] != item["id"] and r.get("category") == item.get("category")][:6]
        ctx = article_page(item, "../", site, cats, related)
        ctx.update({"page_title": ctx["title"] + " | " + esc(site["name"]),
                    "page_description": ctx["description"], "og_type": "article"})
        filename = "%s.html" % item["id"]
        wanted.add(filename)
        write(NEWS_DIR / filename, render(article_tpl, page_ctx("../", ctx)))

    # remove pages for stories that have dropped out
    removed = 0
    for f in NEWS_DIR.glob("*.html"):
        if f.name not in wanted:
            f.unlink()
            removed += 1

    if site.get("site_url"):
        write(SITE / "rss.xml", rss_xml(site, items))
        write(SITE / "sitemap.xml", sitemap_xml(site, items))

    if verbose:
        local = sum(1 for i in items if i.get("type") == "local")
        print("Built site: %d stories (%d own posts, %d fetched), %d old pages removed -> %s"
              % (len(items), local, len(items) - local, removed, SITE))
    return len(items)


if __name__ == "__main__":
    build()
    sys.exit(0)
