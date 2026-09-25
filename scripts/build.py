#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
    text = re.sub(r"[ \t]+(?=\r?\n|$)", "", text)
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


def hold_reason(item):
    """Return why a fetched story should be held back from the site.

    Everything the reader sees is our own Tamil writing, so a fetched story is only
    publishable once scripts/ai_enrich.py has rewritten it. That single rule also
    keeps out headline-only stubs and untranslated English, which is what a story
    without a rewrite always is.
    """
    if item.get("type") == "local":
        return ""
    if not item.get("ai_body"):
        return "not rewritten in Tamil yet" if not item.get("ai_thin") else "too little to report"
    title = re.sub(r"\s+", " ", (item.get("ai_title") or "").strip())
    letters = re.sub(r"[^\w\u0B80-\u0BFF]+", "", title, flags=re.UNICODE)
    if len(letters) < 10 or len(title.split()) < 2:
        return "headline too short"
    return ""


def headline_words(item):
    """Meaningful words of a story's Tamil headline, for spotting repeats."""
    title = (item.get("ai_title") or item.get("title") or "").lower()
    return {w for w in re.findall(r"[\w஀-௿]+", title, flags=re.UNICODE) if len(w) >= 4}


def drop_repeats(items, threshold=0.6):
    """Keep one story per event.

    Several outlets cover the same announcement, and each is rewritten separately, so
    the usual identical-headline check never fires. Compare the words of the Tamil
    headlines instead and keep the story that was published first.
    """
    kept, seen = [], []
    for item in items:
        words = headline_words(item)
        if len(words) >= 3:
            duplicate = False
            for other in seen:
                overlap = len(words & other)
                if overlap and overlap / float(min(len(words), len(other))) >= threshold:
                    duplicate = True
                    break
            if duplicate:
                continue
            seen.append(words)
        kept.append(item)
    return kept


def display(i):
    """What the reader sees: our own Tamil headline, lede and report."""
    out = dict(i)
    if i.get("ai_title"):
        out["title"] = i["ai_title"]
    if i.get("ai_summary"):
        out["summary"] = i["ai_summary"]
    if i.get("ai_body"):
        out["body_paragraphs"] = i["ai_body"]
        out["ai"] = True
    return out


def client_item(i):
    """The subset of fields the browser needs."""
    i = display(i)
    keep = ("id", "type", "title", "summary", "image", "category", "tags",
            "published", "images", "videos", "breaking", "featured", "ai")
    out = {k: i[k] for k in keep if i.get(k) not in (None, "", [], False)}
    if i.get("type") == "local" and i.get("body") and not i.get("summary"):
        out["summary"] = i["body"][:220].rsplit(" ", 1)[0] + "…" if len(i["body"]) > 220 else i["body"]
    return out


def home_thumb_html(item, cats, eager=False):
    cat = cats.get(item.get("category"), {"name": "செய்தி", "color": "#8b1e1e"})
    img = item.get("image") or ((item.get("images") or [None])[0])
    placeholder = ('<div class="ph" style="--c:%s"><span class="ph-cat">%s</span></div>'
                   % (cat["color"], esc(cat["name"])))
    image = ""
    if img:
        image = ('<img src="%s" alt="" %sreferrerpolicy="no-referrer" style="position:relative" '
                 'onerror="this.remove()">'
                 % (esc(img), "" if eager else 'loading="lazy" '))
    return '<div class="thumb">%s%s</div>' % (placeholder, image)


def home_meta_html(item):
    return ('<div class="meta"><time datetime="%s">%s</time></div>'
            % (esc(item.get("published", "")),
               esc(tamil_date(parse_date(item.get("published")), with_time=False))))


def home_badge_html(item, cats):
    cat = cats.get(item.get("category"), {"name": "செய்தி", "color": "#8b1e1e"})
    return '<span class="cat-badge" style="--c:%s">%s</span>' % (cat["color"], esc(cat["name"]))


def home_card_html(item, cats):
    summary = ('<p class="card-summary">%s</p>' % esc(item["summary"])) if item.get("summary") else ""
    return ('<article class="card">%s%s<div class="card-body"><h3 class="card-title">'
            '<a href="news/%s.html">%s</a></h3>%s<div class="card-foot">%s</div></div></article>'
            % (home_badge_html(item, cats), home_thumb_html(item, cats), esc(item["id"]),
               esc(item["title"]), summary, home_meta_html(item)))


def home_lead_html(item, cats):
    summary = ('<p class="lead-summary">%s</p>' % esc(item["summary"])) if item.get("summary") else ""
    return ('<a class="lead" href="news/%s.html">%s<div class="lead-body">%s'
            '<h2 class="lead-title">%s</h2>%s%s</div></a>'
            % (esc(item["id"]), home_thumb_html(item, cats, eager=True), home_badge_html(item, cats),
               esc(item["title"]), summary, home_meta_html(item)))


def home_mini_html(item, cats):
    return ('<a class="mini" href="news/%s.html">%s<div><h3 class="mini-title">%s</h3>%s</div></a>'
            % (esc(item["id"]), home_thumb_html(item, cats), esc(item["title"]), home_meta_html(item)))


def home_initial_content(items, cats, site):
    """Render the first meaningful homepage view; JavaScript progressively enhances it."""
    shown = [client_item(i) for i in items]
    if not shown:
        return "", "", "", "0 செய்திகள்", ""
    featured = [i for i in shown if i.get("featured")]
    recent_cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=36)
    local = [i for i in shown if i.get("category") == "jaffna" and i.get("image")
             and parse_date(i.get("published")) >= recent_cutoff]
    with_image = [i for i in shown if i.get("image")]
    lead = (featured or local or with_image or shown)[0]
    side = [i for i in shown if i is not lead][:4]
    used_ids = {i["id"] for i in [lead] + side}
    page_items = [i for i in shown if i["id"] not in used_ids][:site.get("home_page_size", 12)]
    hero = home_lead_html(lead, cats) + '<div class="hero-side">%s</div>' % "".join(
        home_mini_html(i, cats) for i in side)
    grid = "".join(home_card_html(i, cats) for i in page_items)
    latest = "".join(
        '<li><a href="news/%s.html"><span class="r-title">%s</span><span class="r-meta">%s</span></a></li>'
        % (esc(i["id"]), esc(i["title"]),
           esc(tamil_date(parse_date(i.get("published")), with_time=False))) for i in shown[:6])
    chips = "".join(
        '<a class="chip%s" href="#cat=%s">%s</a>'
        % (" active" if c["id"] == "all" else "", esc(c["id"]), esc(c["name"]))
        for c in ([{"id": "all", "name": "அனைத்தும்"}] + site.get("categories", [])
                  + [{"id": "video", "name": "காணொளி"}]))
    return hero, grid, latest, "%d செய்திகள்" % len(shown), chips


def static_pages(site):
    contact = site.get("contact_email", "").strip()
    contact_link = ('<a href="mailto:%s">%s</a>' % (esc(contact), esc(contact))) if contact else ""
    contact_status = ("<p class=\"info-note\">எம்மைத் தொடர்புகொள்ள: %s</p>" % contact_link
                      if contact_link else
                      '<p class="info-note">தொடர்பு மின்னஞ்சல் தற்போது புதுப்பிக்கப்படுகிறது. அது சேர்க்கப்பட்டதும் இந்தப் பக்கத்தில் காட்டப்படும்.</p>')
    return [
        {
            "slug": "about",
            "heading": "எம்மைப் பற்றி",
            "intro": "யாழ்ப்பாணம், வடமாகாணம் மற்றும் இலங்கையின் முக்கியச் செய்திகளை, எங்கள் சொந்த எழுத்தில் தமிழில் வாசிக்கத் தரும் செய்தித் தளம்.",
            "description": "யாழ் முரசு செய்தித் தளத்தின் நோக்கம் மற்றும் செய்தி தயாரிக்கப்படும் முறை.",
            "content": """
<section><h2>எங்கள் நோக்கம்</h2><p>யாழ்ப்பாணம், வடமாகாணம், இலங்கை, உலகம் மற்றும் விளையாட்டுச் செய்திகளை — முழுமையாக, தெளிவான இலங்கைத் தமிழில், ஒரே இடத்தில் — வாசகருக்குத் தருவதே எங்கள் நோக்கம்.</p></section>
<section><h2>செய்திகள் எவ்வாறு தயாரிக்கப்படுகின்றன?</h2><p>நிறுவப்பட்ட, நம்பகமான செய்தி நிறுவனங்கள் வெளியிடும் அறிக்கைகளை நாங்கள் தொடர்ந்து வாசிக்கிறோம். ஒவ்வொரு செய்தியையும் அதிலுள்ள உண்மைத் தகவல்களைக் கொண்டு <strong>எங்கள் சொந்த வார்த்தைகளில் புதிதாக எழுதுகிறோம்</strong>. எந்த வெளியீட்டாளரின் உரையையும் அப்படியே மீள்பதிப்பிப்பதில்லை.</p><p>செய்தி ஆங்கிலத்தில் வெளியாகியிருந்தால், அது தமிழில் எழுதப்பட்டே வெளியிடப்படும். எனவே தளத்தில் உள்ள அனைத்துச் செய்திகளும் தமிழில் இருக்கும்.</p></section>
<section><h2>தானியங்கி உதவி</h2><p>செய்திகளை வாசித்துத் தமிழில் எழுதுவதற்குத் தானியங்கி (AI) உதவி பயன்படுத்தப்படுகிறது. அது மூல அறிக்கையில் உள்ள தகவல்களை மட்டுமே பயன்படுத்த வேண்டும் — புதிய தகவலோ கருத்தோ சேர்க்கப்படுவதில்லை. ஒவ்வொரு செய்திப் பக்கத்திலும் இதற்கான குறிப்பு காட்டப்படுகிறது.</p><p>செய்தி எழுதப் போதுமான தகவல் கிடைக்காதபோது, அரைகுறையான செய்தியை வெளியிடாமல் விட்டுவிடுகிறோம்.</p></section>
""",
        },
        {
            "slug": "editorial-policy",
            "heading": "ஆசிரியர் கொள்கை",
            "intro": "துல்லியம், வெளிப்படைத்தன்மை மற்றும் வாசகரின் நம்பிக்கை ஆகியவை எங்கள் வெளியீட்டு முடிவுகளின் அடிப்படை.",
            "description": "யாழ் முரசின் செய்தித் தேர்வு, எழுதும் முறை, தானியங்கி உதவி மற்றும் வெளியீட்டு தரநிலைகள்.",
            "content": """
<section><h2>எந்தச் செய்திகள்?</h2><ul><li>நிறுவப்பட்ட, நம்பகமான செய்தி நிறுவனங்கள் வெளியிட்ட அறிக்கைகளை மட்டுமே அடிப்படையாகக் கொள்கிறோம்.</li><li>வதந்திகள், உறுதிப்படுத்தப்படாத சமூக ஊடகக் கூற்றுகள் செய்தியாக எடுக்கப்படுவதில்லை.</li></ul></section>
<section><h2>எழுதும் முறை</h2><ul><li>ஒவ்வொரு செய்தியும் மூல அறிக்கையிலுள்ள உண்மைத் தகவல்களைக் கொண்டு எங்கள் சொந்த வார்த்தைகளில் எழுதப்படுகிறது.</li><li>எந்த வெளியீட்டாளரின் வாக்கியங்களும் அப்படியே நகலெடுக்கப்படுவதில்லை.</li><li>மூலத்தில் இல்லாத எந்தத் தகவலும், பெயரும், எண்ணும் சேர்க்கப்படுவதில்லை.</li><li>ஆங்கிலச் செய்திகள் தமிழில் எழுதப்பட்ட பின்னரே வெளியிடப்படும்.</li></ul></section>
<section><h2>வெளியிடாமல் விடப்படுபவை</h2><ul><li>செய்தி எழுதப் போதுமான தகவல் இல்லாத, வெறும் தலைப்பு மட்டுமான பதிவுகள்.</li><li>சேதமடைந்த அல்லது முற்றுப்பெறாத தலைப்புகள்.</li><li>இவை வாசகருக்குக் காட்டப்படுவதில்லை; தேவையான தகவல் கிடைத்ததும் மீள்பரிசீலிக்கப்படும்.</li></ul></section>
<section><h2>தானியங்கி உதவி</h2><p>செய்திகளை வாசித்துத் தமிழில் எழுதுவதற்குத் தானியங்கி (AI) உதவி பயன்படுத்தப்படுகிறது. அது மூல அறிக்கையில் உள்ள தகவல்களை மட்டுமே பயன்படுத்த வேண்டும்; புதிய தகவல், கருத்து அல்லது உறுதிப்படுத்தப்படாத கூற்று சேர்க்கப்படக்கூடாது. ஒவ்வொரு செய்திப் பக்கத்திலும் இதற்கான குறிப்பு காட்டப்படும்.</p></section>
<section><h2>விளம்பரமும் ஆசிரியர் சுதந்திரமும்</h2><p>விளம்பர உள்ளடக்கம் “விளம்பரம்” என்று தெளிவாகக் குறிக்கப்படும். விளம்பர உறவுகள் செய்தித் தேர்வு அல்லது செய்தியின் தொனியை நிர்ணயிக்கக் கூடாது.</p></section>
""",
        },
        {
            "slug": "corrections",
            "heading": "திருத்தங்கள்",
            "intro": "பிழை இருப்பதை அறிந்தவுடன் அதை விரைவாகவும் வெளிப்படையாகவும் திருத்துவது வாசகர்களிடம் எங்களுக்குள்ள பொறுப்பு.",
            "description": "யாழ் முரசில் செய்திப் பிழைகளை அறிவிக்கும் மற்றும் திருத்தும் நடைமுறை.",
            "content": """
<section><h2>பிழையை அறிவிக்க</h2><p>செய்தியின் தலைப்பு, பக்க இணைப்பு, தவறாக இருப்பதாக நினைக்கும் பகுதி மற்றும் சரியான தகவலுக்கான ஆதாரத்தை அனுப்புங்கள்.</p>%s</section>
<section><h2>நாங்கள் என்ன செய்வோம்?</h2><ul><li>அறிவிப்பை, நாங்கள் செய்தியை எழுதப் பயன்படுத்திய அறிக்கையுடன் ஒப்பிட்டுச் சரிபார்ப்போம்.</li><li>எங்கள் எழுத்தில் பிழை இருந்தால் அதை உடனே திருத்துவோம், அல்லது செய்தியைத் தற்காலிகமாக மறைப்போம்.</li><li>மூல அறிக்கை பின்னர் திருத்தப்பட்டாலோ திரும்பப் பெறப்பட்டாலோ, எங்கள் செய்தியையும் மீளாய்வு செய்வோம்.</li></ul></section>
""" % contact_status,
        },
        {
            "slug": "privacy",
            "heading": "தனியுரிமை",
            "intro": "இந்தத் தளத்தை வாசிக்க கணக்கு தேவையில்லை. தளம் இயங்கத் தேவையான குறைந்தபட்ச தகவல் மட்டுமே பயன்படுத்தப்படுகிறது.",
            "description": "யாழ் முரசு இணையத்தளத்தின் தனியுரிமை மற்றும் வெளிப்புற சேவைகள் பற்றிய தகவல்.",
            "content": """
<section><h2>இந்தத் தளம் சேமிப்பது</h2><p>நீங்கள் தேர்ந்தெடுக்கும் ஒளி அல்லது இருள் தோற்றம் உங்கள் உலாவியில் உள்ளூர் அமைப்பாகச் சேமிக்கப்படும். இது உங்களை அடையாளம் காண பயன்படுத்தப்படாது.</p></section>
<section><h2>வெளிப்புற இணைப்புகள் மற்றும் ஊடகம்</h2><p>செய்தி மூலங்கள், காணொளிகள் மற்றும் சமூகப் பகிர்வு சேவைகள் வெளிப்புற தளங்களுக்கு வழிநடத்தலாம். அவற்றைத் திறக்கும் போது அந்தச் சேவைகளின் தனியுரிமைக் கொள்கைகள் பொருந்தும்.</p></section>
<section><h2>விளம்பரங்கள்</h2><p>எதிர்காலத்தில் விளம்பர வலைப்பின்னல் பயன்படுத்தப்பட்டால், அது குக்கிகள் அல்லது சாதனத் தகவலைப் பயன்படுத்தலாம். அத்தகைய சேவை செயல்படுத்தப்படும் போது இந்தக் கொள்கை அதற்கேற்ப புதுப்பிக்கப்படும்.</p></section>
<section><h2>சேவைப் பதிவுகள்</h2><p>தளத்தை வழங்கும் சேவை பாதுகாப்பு, பிழை கண்டறிதல் மற்றும் போக்குவரத்து அளவீட்டுக்காக IP முகவரி, உலாவி வகை மற்றும் கோரிக்கை நேரம் போன்ற வழக்கமான தொழில்நுட்பப் பதிவுகளை வைத்திருக்கலாம்.</p></section>
""",
        },
        {
            "slug": "contact",
            "heading": "தொடர்பு",
            "intro": "செய்தித் திருத்தம், உள்ளூர் தகவல், விளம்பரம் அல்லது தளத்தைப் பற்றிய கருத்தை சரியான விவரங்களுடன் அனுப்புங்கள்.",
            "description": "யாழ் முரசை செய்தித் திருத்தம், தகவல் மற்றும் விளம்பர விசாரணைகளுக்குத் தொடர்புகொள்ளும் வழி.",
            "content": """
<section>%s<div class="contact-cards"><div class="contact-card"><h3>செய்தித் திருத்தம்</h3><p>செய்திப் பக்க இணைப்பு, திருத்த வேண்டிய பகுதி மற்றும் நம்பகமான ஆதாரத்தை குறிப்பிடுங்கள்.</p></div><div class="contact-card"><h3>உள்ளூர் தகவல்</h3><p>நிகழ்வின் இடம், தேதி, நேரம் மற்றும் உறுதிப்படுத்தக்கூடிய ஆதாரங்களை அனுப்புங்கள்.</p></div><div class="contact-card"><h3>விளம்பரம்</h3><p>விளம்பர வடிவம், காலம் மற்றும் தொடர்பு விபரங்களைச் சேர்க்கவும். விளம்பரங்கள் தெளிவாகக் குறிக்கப்படும்.</p></div></div></section>
""" % contact_status,
        },
    ]


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
  <button class="sh sh-fb" type="button" data-net="facebook" aria-label="Facebook இல் பகிர்க"><svg class="i"><use href="#i-fb"/></svg><span>Facebook</span></button>
  <button class="sh sh-x" type="button" data-net="x" aria-label="X இல் பகிர்க"><svg class="i"><use href="#i-x"/></svg></button>
  <button class="sh sh-ig" type="button" data-net="instagram" aria-label="Instagram இல் பகிர்க"><svg class="i"><use href="#i-ig"/></svg><span>Instagram</span></button>
  <button class="sh sh-wa" type="button" data-net="whatsapp" aria-label="WhatsApp இல் பகிர்க"><svg class="i"><use href="#i-wa"/></svg><span>WhatsApp</span></button>
  <button class="sh sh-copy" type="button" data-net="copy" aria-label="இணைப்பை நகலெடு"><svg class="i"><use href="#i-link"/></svg></button>
</div>""" % extra_class


def paragraphs(text):
    parts = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    return "\n".join("<p>%s</p>" % esc(p).replace("\n", "<br>") for p in parts)


def placeholder_html(item, cats):
    cat = cats.get(item.get("category"), {"name": "", "color": "#8b1e1e"})
    return ('<div class="ph" style="--c:%s"><span class="ph-cat">%s</span></div>'
            % (cat["color"], esc(cat["name"])))


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
                   % "".join('<button class="gallery-item" type="button" data-lightbox="%d" '
                             'aria-label="படம் %d ஐப் பெரிதாக்குக"><img src="%s" alt="%s — படம் %d" loading="lazy"></button>'
                             % (n, n + 1, esc(src), esc(item["title"]), n + 1) for n, src in enumerate(images)))
    videos = ""
    if item.get("videos"):
        videos = ('<section class="videos"><h2 class="block-title">காணொளிகள்</h2>%s</section>'
                  % "".join(video_html(v, base) for v in item["videos"]))

    if is_local:
        body = paragraphs(item.get("body") or item.get("summary", ""))
        summary = '<p class="lede">%s</p>' % esc(item["summary"]) if item.get("summary") and item.get("body") else ""
        note = ""
        byline = esc(item.get("author") or site["name"])
    else:
        summary = ""
        parts = []
        body_parts = item.get("body_paragraphs", [])
        lede = item.get("summary", "")
        # The lede is a separate one-line summary, but it can come back as the opening
        # sentence of the report. Printing both would just repeat it to the reader.
        if lede and not (body_parts and body_parts[0].startswith(lede.rstrip("… ")[:60])):
            parts.append('<p class="lede">%s</p>' % esc(lede))
        parts += ["<p>%s</p>" % esc(p) for p in body_parts]
        body = "\n".join(parts)
        note = ('<p class="ai-note">இந்தச் செய்தி, வெளியான தகவல்களின் அடிப்படையில் '
                'தானியங்கி உதவியுடன் தமிழில் எழுதப்பட்டது.</p>')
        byline = esc(site["name"])

    related_html = "".join(
        '<li><a href="%s.html"><span class="rel-title">%s</span><span class="rel-meta">%s</span></a></li>'
        % (esc(r["id"]), esc(r["title"]),
           esc(tamil_date(parse_date(r.get("published")), with_time=False))) for r in related)

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
        "hero": hero,
        "summary": summary,
        "body": body,
        "gallery": gallery,
        "videos": videos,
        "ai_note": note,
        "share_top": share_bar(),
        "share_bottom": share_bar("share-bottom"),
        "related": related_html,
        "images_json": esc(json.dumps(images or ([hero_img] if hero_img else []), ensure_ascii=False)),
        "author_name": item.get("author") or site["name"],
        "hero_image_url": og_image if og_image.startswith("http") else "",
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


def sitemap_xml(site, items, pages=None):
    url = site["site_url"].rstrip("/")
    locs = ["<url><loc>%s/</loc></url>" % url]
    locs += ["<url><loc>%s/%s.html</loc></url>" % (url, p["slug"]) for p in (pages or [])]
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
    assessed = [(i, hold_reason(i)) for i in collect_items(site)]
    held = [(i, reason) for i, reason in assessed if reason]
    items = drop_repeats([i for i, reason in assessed if not reason])

    # Every fetched story has to be rewritten in Tamil before it can be published, so a
    # broken or unconfigured AI step would otherwise quietly empty the site. Rather than
    # publish a near-empty front page, leave the pages already in site/ exactly as they are.
    floor = site.get("min_publishable", 8)
    if len(items) < floor and held:
        print("REFUSING TO BUILD: only %d stories are ready to publish (need %d), and %d are "
              "waiting to be rewritten.\nThe site in site/ has been left untouched.\n"
              "Most likely ANTHROPIC_API_KEY is not set, so scripts/ai_enrich.py cannot "
              "write anything." % (len(items), floor, len(held)))
        return 0

    pages = static_pages(site)
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
            "contact_line": ('<p class="small">விளம்பரங்களுக்கு: <a href="mailto:%s">%s</a></p>'
                             % (esc(site["contact_email"]), esc(site["contact_email"])))
                            if site.get("contact_email") else "",
            "canonical_tag": "",
            "structured_data": "",
            "data_script": "",
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
    compact_data = {"generated": data["generated"], "site": public_site, "ads": ads,
                    "items": [client_item(i) for i in items[:12]]}
    write(SITE / "data" / "chrome.js",
          "window.NEWS_DATA = " + json.dumps(compact_data, ensure_ascii=False, separators=(",", ":")) + ";\n")

    # home page
    index_tpl = (TEMPLATES / "index.html").read_text(encoding="utf-8")
    home_hero, home_grid, home_latest, home_count, home_chips = home_initial_content(items, cats, site)
    home_url = site.get("site_url", "").rstrip("/") + "/" if site.get("site_url") else ""
    home_schema = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": site["name"],
        "alternateName": site.get("name_en", ""),
        "url": home_url,
        "inLanguage": "ta-LK",
        "description": site.get("description", ""),
        "potentialAction": {
            "@type": "SearchAction",
            "target": home_url + "?q={search_term_string}",
            "query-input": "required name=search_term_string",
        } if home_url else None,
    }
    home_schema = {k: v for k, v in home_schema.items() if v not in (None, "")}
    write(SITE / "index.html", render(index_tpl, page_ctx("", {
        "page_title": esc(site["name"]) + " — " + esc(site.get("tagline", "")),
        "page_description": esc(site.get("description", "")),
        "page_url": esc(site.get("site_url", "")),
        "og_image": "",
        "og_type": "website",
        "canonical_tag": '<link rel="canonical" href="%s">' % esc(home_url) if home_url else "",
        "structured_data": '<script type="application/ld+json">%s</script>' % json.dumps(home_schema, ensure_ascii=False).replace("</", "<\\/"),
        "data_script": '<script src="data/news.js?v=%s"></script>' % version,
        "home_hero": home_hero,
        "home_grid": home_grid,
        "home_latest": home_latest,
        "home_count": home_count,
        "home_chips": home_chips,
    })))

    # story pages
    article_tpl = (TEMPLATES / "article.html").read_text(encoding="utf-8")
    wanted = set()
    for item in (display(i) for i in items):
        related = [display(r) for r in items if r["id"] != item["id"] and r.get("category") == item.get("category")][:6]
        ctx = article_page(item, "../", site, cats, related)
        article_schema = {
            "@context": "https://schema.org",
            "@type": "NewsArticle",
            "headline": item["title"],
            "description": html.unescape(ctx["description"]),
            "datePublished": ctx["iso"],
            "dateModified": ctx["iso"],
            "inLanguage": "ta-LK",
            "mainEntityOfPage": {"@type": "WebPage", "@id": html.unescape(ctx["page_url"])},
            "author": {"@type": "Organization", "name": ctx["author_name"]},
            "publisher": {
                "@type": "NewsMediaOrganization",
                "name": site["name"],
                "url": site.get("site_url", ""),
                "logo": {"@type": "ImageObject", "url": site.get("site_url", "").rstrip("/") + "/assets/img/logo.svg"},
            },
        }
        if ctx["hero_image_url"]:
            article_schema["image"] = [ctx["hero_image_url"]]
        ctx.update({"page_title": ctx["title"] + " | " + esc(site["name"]),
                    "page_description": ctx["description"], "og_type": "article",
                    "canonical_tag": '<link rel="canonical" href="%s">' % ctx["page_url"] if ctx["page_url"] else "",
                    "structured_data": '<script type="application/ld+json">%s</script>' % json.dumps(article_schema, ensure_ascii=False).replace("</", "<\\/"),
                    "data_script": '<script src="../data/chrome.js?v=%s"></script>' % version})
        filename = "%s.html" % item["id"]
        wanted.add(filename)
        write(NEWS_DIR / filename, render(article_tpl, page_ctx("../", ctx)))

    # trust, editorial and contact pages
    page_tpl = (TEMPLATES / "page.html").read_text(encoding="utf-8")
    for page in pages:
        page_url = "%s/%s.html" % (site.get("site_url", "").rstrip("/"), page["slug"])
        page_schema = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": page["heading"],
            "description": page["description"],
            "url": page_url,
            "inLanguage": "ta-LK",
            "isPartOf": {"@type": "WebSite", "name": site["name"], "url": site.get("site_url", "")},
        }
        page_ctx_data = {
            "page_title": esc(page["heading"]) + " | " + esc(site["name"]),
            "page_description": esc(page["description"]),
            "page_url": esc(page_url),
            "og_image": "",
            "og_type": "website",
            "canonical_tag": '<link rel="canonical" href="%s">' % esc(page_url),
            "structured_data": '<script type="application/ld+json">%s</script>' % json.dumps(page_schema, ensure_ascii=False).replace("</", "<\\/"),
            "data_script": '<script src="data/chrome.js?v=%s"></script>' % version,
            "page_heading": esc(page["heading"]),
            "page_intro": esc(page["intro"]),
            "page_content": page["content"],
        }
        write(SITE / (page["slug"] + ".html"), render(page_tpl, page_ctx("", page_ctx_data)))

    # remove pages for stories that have dropped out
    removed = 0
    for f in NEWS_DIR.glob("*.html"):
        if f.name not in wanted:
            f.unlink()
            removed += 1

    if site.get("site_url"):
        write(SITE / "rss.xml", rss_xml(site, items))
        write(SITE / "sitemap.xml", sitemap_xml(site, items, pages))

    if verbose:
        local = sum(1 for i in items if i.get("type") == "local")
        print("Built site: %d stories (%d own posts, %d fetched), %d quality-held, %d old pages removed -> %s"
              % (len(items), local, len(items) - local, len(held), removed, SITE))
    return len(items)


if __name__ == "__main__":
    build()
    sys.exit(0)
