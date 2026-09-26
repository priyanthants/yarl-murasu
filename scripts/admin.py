#!/usr/bin/env python3
"""Local admin panel: add your own news (photos + video links), manage ads,
fetch the latest news, and preview the site.

    python3 scripts/admin.py            # then open http://localhost:8000/admin
    python3 scripts/admin.py --port 9000

It listens on 127.0.0.1 only, so it is reachable from this computer alone.
"""
import argparse
import datetime as dt
import hashlib
import html
import json
import os
import subprocess
import sys
import urllib.parse
from email.parser import BytesParser
from email.policy import default as email_policy
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
POSTS = ROOT / "content" / "posts.json"
ADS = ROOT / "config" / "ads.json"
SITE_CFG = ROOT / "config" / "site.json"
UPLOADS = SITE / "uploads"
MAX_UPLOAD = 40 * 1024 * 1024
IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}
VIDEO_TYPES = {".mp4", ".webm"}
SL_TZ = dt.timezone(dt.timedelta(hours=5, minutes=30))

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402

esc = html.escape
SLOTS = [("header", "தலைப்பு (728×90)"), ("sidebar", "பக்கப்பட்டி (300×250)"), ("in_feed", "செய்திகளுக்கு இடையில்"),
         ("article", "செய்திப் பக்கத்தினுள்"), ("footer", "அடிக்குறிப்பு (970×90)")]


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def save_upload(filename, data, allowed):
    ext = Path(filename).suffix.lower()
    if ext not in allowed or not data:
        return None
    folder = UPLOADS / dt.date.today().strftime("%Y-%m")
    folder.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha1(data).hexdigest()[:16] + ext
    (folder / name).write_bytes(data)
    return "uploads/%s/%s" % (folder.name, name)


def lines(text):
    return [l.strip() for l in (text or "").splitlines() if l.strip()]


# ---------------------------------------------------------------- page

STYLE = """
*{box-sizing:border-box}body{margin:0;font:15px/1.6 "Noto Sans Tamil",system-ui,sans-serif;background:#f4efe7;color:#1d1714}
header{background:#8b1e1e;color:#fff;padding:14px 24px;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
header h1{margin:0;font-size:20px}header a{color:#ffe7a8;font-weight:600}
main{max-width:1100px;margin:0 auto;padding:20px 16px 60px;display:grid;gap:22px}
.card{background:#fff;border-radius:14px;padding:20px 22px;box-shadow:0 2px 14px rgba(60,30,10,.08)}
h2{margin:0 0 14px;font-size:19px;color:#8b1e1e}label{display:block;font-weight:600;margin:12px 0 4px;font-size:14px}
input[type=text],input[type=url],input[type=date],input[type=datetime-local],textarea,select{width:100%;padding:9px 11px;border:1px solid #d9cdbd;border-radius:9px;font:inherit;background:#fffdf9}
textarea{min-height:90px;resize:vertical}.row{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:0 16px}
.hint{font-size:12.5px;color:#7a6e64;font-weight:400}.checks{display:flex;gap:20px;margin-top:12px;flex-wrap:wrap}.checks label{display:flex;gap:6px;align-items:center;margin:0;font-weight:500}
button,.btn{background:#8b1e1e;color:#fff;border:0;border-radius:999px;padding:10px 22px;font:inherit;font-weight:700;cursor:pointer;display:inline-block;text-decoration:none}
button.secondary{background:#e0a526;color:#1d1714}button.danger{background:#fff;color:#b42323;border:1px solid #e3b7b7;padding:5px 12px;font-size:13px}
.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px}.msg{background:#e8f6ec;border:1px solid #a9dbb8;color:#14532d;padding:10px 14px;border-radius:10px}
.msg.err{background:#fdeaea;border-color:#f1b5b5;color:#7f1d1d}
table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:9px 6px;border-bottom:1px solid #eee3d6;text-align:left;vertical-align:top}
th{font-size:12.5px;color:#7a6e64;font-weight:600}.thumb{width:64px;height:44px;object-fit:cover;border-radius:6px;background:#eee}
.tag{display:inline-block;font-size:11.5px;padding:1px 8px;border-radius:999px;background:#f4e6c8;margin-right:4px}
pre{background:#1d1714;color:#f3e7d6;padding:12px;border-radius:10px;overflow:auto;font-size:12.5px;max-height:260px}
.tabs{display:flex;gap:6px;margin-bottom:6px}
"""


def page(msg="", err=False, log=""):
    site = load(SITE_CFG, {})
    posts = load(POSTS, [])
    ads = load(ADS, {"slots": {}})
    cats = site.get("categories", [])
    now = dt.datetime.now(SL_TZ).strftime("%Y-%m-%dT%H:%M")

    cat_opts = "".join('<option value="%s">%s</option>' % (esc(c["id"]), esc(c["name"])) for c in cats)
    slot_opts = "".join('<option value="%s">%s</option>' % s for s in SLOTS)

    rows = []
    for p in sorted(posts, key=lambda p: p.get("published", ""), reverse=True):
        img = (p.get("images") or [None])[0]
        flags = "".join('<span class="tag">%s</span>' % t for t, on in
                        (("முக்கியம்", p.get("breaking")), ("முதன்மை", p.get("featured")), ("வரைவு", p.get("draft"))) if on)
        rows.append("""<tr><td>%s</td><td><a href="/news/%s.html" target="_blank">%s</a><br>%s
<span class="hint">%d படம் · %d காணொளி</span></td><td class="hint">%s</td>
<td><form method="post" action="/admin/post/delete" onsubmit="return confirm('இந்தச் செய்தியை நீக்கவா?')">
<input type="hidden" name="id" value="%s"><button class="danger">நீக்கு</button></form></td></tr>""" % (
            '<img class="thumb" src="/%s">' % esc(img) if img else "", esc(p["id"]), esc(p["title"]), flags,
            len(p.get("images", [])), len(p.get("videos", [])), esc(p.get("published", "")[:16].replace("T", " ")), esc(p["id"])))
    posts_table = ("<table><tr><th></th><th>தலைப்பு</th><th>திகதி</th><th></th></tr>%s</table>" % "".join(rows)
                   if rows else '<p class="hint">இன்னும் சொந்தச் செய்திகள் இல்லை.</p>')

    ad_rows = []
    for slot, label in SLOTS:
        for ad in ads.get("slots", {}).get(slot, []):
            what = ('<img class="thumb" src="%s">' % esc(ad["image"] if ad["image"].startswith("http") else "/" + ad["image"])
                    if ad.get("type") == "image" and ad.get("image") else '<span class="tag">HTML</span>')
            period = " → ".join(x for x in (ad.get("start", ""), ad.get("end", "")) if x) or "எப்போதும்"
            ad_rows.append("""<tr><td>%s</td><td>%s<br><span class="hint">%s</span></td><td class="hint">%s</td>
<td><form method="post" action="/admin/ad/delete" onsubmit="return confirm('இந்த விளம்பரத்தை நீக்கவா?')">
<input type="hidden" name="id" value="%s"><button class="danger">நீக்கு</button></form></td></tr>""" % (
                what, esc(ad.get("name") or ad.get("alt") or ad["id"]), esc(label), esc(period), esc(ad["id"])))
    ads_table = ("<table><tr><th></th><th>விளம்பரம்</th><th>காலம்</th><th></th></tr>%s</table>" % "".join(ad_rows)
                 if ad_rows else '<p class="hint">விளம்பரங்கள் இல்லை — தளத்தில் "உங்கள் விளம்பரம் இங்கே" இடம் காட்டப்படும்.</p>')

    card_files = sorted((SITE / "cards").glob("*.png"), key=lambda f: f.stat().st_mtime, reverse=True)[:3]
    cards_html = "".join(
        '<figure style="display:inline-block;margin:14px 14px 0 0;text-align:center">'
        '<img src="/cards/%s" style="width:210px;border-radius:12px;border:1px solid #e3d8c8">'
        '<figcaption class="hint"><a href="/cards/%s" download>%s ⤓</a></figcaption></figure>'
        % (esc(f.name), esc(f.name), esc(f.name)) for f in card_files)
    ai_cfg = load(ROOT / "config" / "ai.json", {})
    provider = ai_cfg.get("provider", "gemini")
    key_names = {"gemini": ("GEMINI_API_KEY",),
                 "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}.get(provider, ())
    has_key = any(os.environ.get(n) for n in key_names)
    model = (ai_cfg.get(provider) or {}).get("model", "")
    fetched = load(ROOT / "data" / "fetched.json", {"items": []}).get("items", [])
    written = sum(1 for i in fetched if i.get("ai_body"))
    waiting = len(fetched) - written
    if has_key:
        ai_state = ("தமிழில் எழுதப்பட்ட செய்திகள்: %d · எழுதக் காத்திருப்பவை: %d · %s (%s)"
                    % (written, waiting, model, provider))
    else:
        ai_state = ("⚠ %s அமைக்கப்படவில்லை. ஒவ்வொரு செய்தியும் தமிழில் மீளெழுதப்பட்ட "
                    "பின்னரே வெளியிடப்படும் — எனவே இது இல்லாமல் புதிய செய்தி எதுவும் "
                    "தளத்தில் வராது. (%d செய்திகள் காத்திருக்கின்றன.)"
                    % (" / ".join(key_names) or "API key", waiting))

    notice = '<div class="msg%s">%s</div>' % (" err" if err else "", esc(msg)) if msg else ""
    log_html = "<pre>%s</pre>" % esc(log) if log else ""

    return """<!doctype html><html lang="ta"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>நிர்வாகம் — %(name)s</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Tamil:wght@400;600;700&display=swap" rel="stylesheet">
<style>%(style)s</style></head><body>
<header><h1>%(name)s — நிர்வாகப் பகுதி</h1><span><a href="/" target="_blank">முன்னோட்டம் ↗</a> &nbsp; <a href="%(live)s" target="_blank">நேரலைத் தளம் ↗</a></span></header>
<main>
%(notice)s
<section class="card">
  <h2>இணையத்தளத்தில் வெளியிடு (Publish to the live website)</h2>
  <p class="hint">இங்கே சேர்த்த செய்திகள், படங்கள், விளம்பரங்கள் முதலில் இந்தக் கணினியில் மட்டுமே இருக்கும். நேரலைத் தளத்தில் காட்ட இந்தப் பொத்தானை அழுத்துங்கள்.
  Posts, photos and ads you add here stay on this computer until you press this button.</p>
  <div class="actions"><form method="post" action="/admin/publish"><button>நேரலையில் வெளியிடு</button></form></div>
</section>
<section class="card">
  <h2>சமீபத்திய செய்திகளைப் பெறுக</h2>
  <p class="hint">நம்பகமான மூலங்களிலிருந்து புதிய செய்திகளைப் பெற்று உள்ளூர் முன்னோட்டத்தைப் புதுப்பிக்கும். நேரலைத் தளம் GitHub மூலம் ஒவ்வொரு 30 நிமிடத்திலும் தானாகப் புதுப்பிக்கப்படுகிறது.
  (Refreshes the local preview. The live site updates itself on GitHub every 30 minutes.)</p>
  <div class="actions">
    <form method="post" action="/admin/fetch"><button>செய்திகளைப் பெறுக</button></form>
    <form method="post" action="/admin/ai"><button class="secondary">தமிழில் எழுதுக / மொழிபெயர்ப்பு</button></form>
    <form method="post" action="/admin/build"><button class="secondary">தளத்தை மட்டும் மீளுருவாக்கு</button></form>
  </div>
  <p class="hint">%(ai_state)s</p>
  %(log)s
</section>

<section class="card">
  <h2>இன்றைய செய்தி அட்டை — Instagram / Facebook</h2>
  <p class="hint">இன்றைய முக்கியச் செய்திகளை ஒரு படமாக உருவாக்கி, Instagram அல்லது WhatsApp இல் பகிரலாம்.
  (Makes a shareable image of today's top headlines.)</p>
  <form method="post" action="/admin/card">
    <div class="row">
      <div><label>அளவு</label><select name="size">
        <option value="square">சதுரம் 1080×1080 (Instagram post)</option>
        <option value="portrait">நெடுக்கு 1080×1350 (Instagram feed)</option>
        <option value="story">Story 1080×1920</option>
      </select></div>
      <div><label>செய்திகளின் எண்ணிக்கை</label><input type="text" name="count" placeholder="தானாக"></div>
      <div><label>பிரிவு <span class="hint">(விரும்பினால்)</span></label><select name="category"><option value="">அனைத்தும்</option>%(cat_opts)s</select></div>
    </div>
    <div class="actions"><button>அட்டையை உருவாக்கு</button></div>
  </form>
  %(cards)s
</section>

<section class="card">
  <h2>புதிய செய்தி சேர்க்க (Add your own news)</h2>
  <form method="post" action="/admin/post" enctype="multipart/form-data">
    <label>தலைப்பு *</label><input type="text" name="title" required>
    <label>சுருக்கம் <span class="hint">— முகப்புப் பக்கத்திலும் பகிர்வுகளிலும் தெரியும் 1–2 வரிகள்</span></label>
    <textarea name="summary" style="min-height:60px"></textarea>
    <label>முழுச் செய்தி <span class="hint">— பந்திகளை வெற்று வரியால் பிரிக்கவும்</span></label>
    <textarea name="body" style="min-height:180px"></textarea>
    <div class="row">
      <div><label>பிரிவு</label><select name="category">%(cat_opts)s</select></div>
      <div><label>எழுதியவர் <span class="hint">(விரும்பினால்)</span></label><input type="text" name="author"></div>
      <div><label>வெளியீட்டு நேரம்</label><input type="datetime-local" name="published" value="%(now)s"></div>
    </div>
    <label>புகைப்படங்கள் பதிவேற்ற <span class="hint">— பல படங்களைத் தெரிவு செய்யலாம் (JPG, PNG, WebP)</span></label>
    <input type="file" name="photos" accept="image/*" multiple>
    <label>புகைப்பட இணைப்புகள் <span class="hint">— ஒரு வரிக்கு ஒரு இணைப்பு (https://…)</span></label>
    <textarea name="image_urls" style="min-height:60px" placeholder="https://example.com/photo.jpg"></textarea>
    <label>படக் குறிப்பு <span class="hint">(விரும்பினால்)</span></label><input type="text" name="caption">
    <label>காணொளி இணைப்புகள் <span class="hint">— YouTube, Facebook, Instagram, TikTok, Vimeo அல்லது .mp4; ஒரு வரிக்கு ஒன்று</span></label>
    <textarea name="video_urls" style="min-height:60px" placeholder="https://www.youtube.com/watch?v=..."></textarea>
    <label>காணொளிக் கோப்பு பதிவேற்ற <span class="hint">(MP4/WebM, 40MB வரை)</span></label>
    <input type="file" name="video_files" accept="video/mp4,video/webm" multiple>
    <div class="checks">
      <label><input type="checkbox" name="breaking"> முக்கிய செய்தி (ticker இல் முதலில்)</label>
      <label><input type="checkbox" name="featured"> முதன்மைச் செய்தி (முகப்பில் பெரிதாக)</label>
      <label><input type="checkbox" name="draft"> வரைவு (வெளியிட வேண்டாம்)</label>
    </div>
    <div class="actions"><button>வெளியிடு</button></div>
  </form>
</section>

<section class="card"><h2>எனது செய்திகள்</h2>%(posts_table)s</section>

<section class="card">
  <h2>விளம்பரம் சேர்க்க (Add an ad)</h2>
  <form method="post" action="/admin/ad" enctype="multipart/form-data">
    <div class="row">
      <div><label>இடம்</label><select name="slot">%(slot_opts)s</select></div>
      <div><label>விளம்பரதாரர் பெயர்</label><input type="text" name="name" required></div>
      <div><label>இணைப்பு (click link)</label><input type="url" name="link" placeholder="https://"></div>
    </div>
    <label>விளம்பரப் படம் பதிவேற்ற</label><input type="file" name="image_file" accept="image/*">
    <label>அல்லது படத்தின் இணைப்பு</label><input type="url" name="image_url" placeholder="https://">
    <label>அல்லது விளம்பரக் குறியீடு <span class="hint">— Google AdSense போன்றவற்றின் HTML/script குறியீடு</span></label>
    <textarea name="code" placeholder="&lt;script async src=...&gt;&lt;/script&gt;"></textarea>
    <div class="row">
      <div><label>தொடக்கத் திகதி <span class="hint">(விரும்பினால்)</span></label><input type="date" name="start"></div>
      <div><label>முடிவுத் திகதி <span class="hint">(விரும்பினால்)</span></label><input type="date" name="end"></div>
    </div>
    <div class="actions"><button>விளம்பரத்தைச் சேர்</button></div>
  </form>
</section>

<section class="card"><h2>விளம்பரங்கள்</h2>%(ads_table)s</section>
</main></body></html>""" % {
        "name": esc(site.get("name", "")), "live": esc(site.get("site_url") or "/"), "style": STYLE,
        "cards": cards_html, "ai_state": ai_state, "notice": notice, "log": log_html, "cat_opts": cat_opts,
        "slot_opts": slot_opts, "now": now, "posts_table": posts_table, "ads_table": ads_table,
    }


# ---------------------------------------------------------------- server

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE), **kwargs)

    def log_message(self, fmt, *args):
        if self.path.startswith("/admin"):
            sys.stderr.write("%s %s\n" % (self.command, self.path))

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_html(self, body, status=200):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path)
        if path.path.rstrip("/") == "/admin":
            q = urllib.parse.parse_qs(path.query)
            return self.send_html(page(q.get("msg", [""])[0], q.get("err", [""])[0] == "1"))
        return super().do_GET()

    def read_form(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD * 4:
            raise ValueError("கோப்பு மிகப் பெரியது")
        body = self.rfile.read(length)
        ctype = self.headers.get("Content-Type", "")
        fields, files = {}, []
        if ctype.startswith("multipart/form-data"):
            msg = BytesParser(policy=email_policy).parsebytes(
                b"Content-Type: " + ctype.encode("latin-1") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body)
            for part in msg.iter_parts():
                name = part.get_param("name", header="content-disposition")
                filename = part.get_filename()
                payload = part.get_payload(decode=True) or b""
                if filename:
                    if payload:
                        files.append((name, filename, payload))
                else:
                    fields[name] = payload.decode("utf-8", "replace")
        else:
            for k, v in urllib.parse.parse_qs(body.decode("utf-8"), keep_blank_values=True).items():
                fields[k] = v[0]
        return fields, files

    def redirect(self, msg, err=False):
        self.send_response(303)
        self.send_header("Location", "/admin?" + urllib.parse.urlencode({"msg": msg, "err": "1" if err else "0"}))
        self.end_headers()

    def do_POST(self):
        route = urllib.parse.urlparse(self.path).path
        try:
            if route == "/admin/fetch":
                out = subprocess.run([sys.executable, str(ROOT / "scripts" / "fetch_news.py")],
                                     capture_output=True, text=True, timeout=2400)
                return self.send_html(page("செய்திகள் பெறப்பட்டு தளம் புதுப்பிக்கப்பட்டது" if out.returncode == 0
                                           else "செய்திகளைப் பெறுவதில் பிழை", out.returncode != 0,
                                           (out.stdout + out.stderr)[-4000:]))
            if route == "/admin/publish":
                out = subprocess.run(["/bin/bash", str(ROOT / "scripts" / "publish.sh")],
                                     capture_output=True, text=True, timeout=300)
                return self.send_html(page("இணையத்தளத்தில் வெளியிடப்பட்டது — ஒரு நிமிடத்தில் நேரலையில் தெரியும்"
                                           if out.returncode == 0 else "வெளியிடுவதில் பிழை", out.returncode != 0,
                                           (out.stdout + out.stderr)[-4000:]))
            if route == "/admin/card":
                fields, _ = self.read_form()
                cmd = [sys.executable, str(ROOT / "scripts" / "make_card.py"),
                       "--size", fields.get("size", "square")]
                if fields.get("count"):
                    cmd += ["--count", fields["count"]]
                if fields.get("category"):
                    cmd += ["--category", fields["category"]]
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                return self.send_html(page("செய்தி அட்டை தயார்" if out.returncode == 0 else "அட்டையை உருவாக்க முடியவில்லை",
                                           out.returncode != 0, (out.stdout + out.stderr)[-2000:]))
            if route == "/admin/ai":
                venv = ROOT / ".venv" / "bin" / "python"
                out = subprocess.run([str(venv) if venv.exists() else sys.executable,
                                      str(ROOT / "scripts" / "ai_enrich.py")],
                                     capture_output=True, text=True, timeout=1800)
                return self.send_html(page("செய்திகள் தமிழில் எழுதப்பட்டன" if out.returncode == 0 else "பிழை",
                                           out.returncode != 0, (out.stdout + out.stderr)[-3000:]))
            if route == "/admin/build":
                try:
                    build.build(verbose=False)
                except build.SiteNotReady as why:
                    return self.redirect("தளம் உருவாக்கப்படவில்லை: %s" % why, err=True)
                return self.redirect("தளம் மீளுருவாக்கப்பட்டது")

            fields, files = self.read_form()
            if route == "/admin/post":
                return self.add_post(fields, files)
            if route == "/admin/post/delete":
                posts = [p for p in load(POSTS, []) if p["id"] != fields.get("id")]
                save(POSTS, posts)
                build.build(verbose=False)
                return self.redirect("செய்தி நீக்கப்பட்டது")
            if route == "/admin/ad":
                return self.add_ad(fields, files)
            if route == "/admin/ad/delete":
                ads = load(ADS, {"slots": {}})
                for slot in ads["slots"]:
                    ads["slots"][slot] = [a for a in ads["slots"][slot] if a["id"] != fields.get("id")]
                save(ADS, ads)
                build.build(verbose=False)
                return self.redirect("விளம்பரம் நீக்கப்பட்டது")
            self.send_error(404)
        except Exception as e:  # show the problem instead of a blank page
            return self.redirect("பிழை: %s" % e, True)

    def add_post(self, f, files):
        title = f.get("title", "").strip()
        if not title:
            return self.redirect("தலைப்பு அவசியம்", True)
        images = [save_upload(fn, data, IMAGE_TYPES) for name, fn, data in files if name == "photos"]
        images = [i for i in images if i] + lines(f.get("image_urls"))
        videos = [save_upload(fn, data, VIDEO_TYPES) for name, fn, data in files if name == "video_files"]
        videos = [v for v in videos if v] + lines(f.get("video_urls"))
        published = f.get("published") or dt.datetime.now(SL_TZ).strftime("%Y-%m-%dT%H:%M")
        stamp = dt.datetime.now(SL_TZ)
        post = {
            "id": "p" + stamp.strftime("%Y%m%d%H%M%S"),
            "title": title,
            "summary": f.get("summary", "").strip(),
            "body": f.get("body", "").strip(),
            "category": f.get("category") or "jaffna",
            "author": f.get("author", "").strip(),
            "images": images,
            "caption": f.get("caption", "").strip(),
            "videos": videos,
            "published": published + ":00+05:30" if len(published) == 16 else published,
            "breaking": "breaking" in f,
            "featured": "featured" in f,
            "draft": "draft" in f,
        }
        post = {k: v for k, v in post.items() if v not in ("", [], False)}
        posts = load(POSTS, [])
        if post.get("featured"):  # only one featured story at a time
            for p in posts:
                p.pop("featured", None)
        posts.append(post)
        save(POSTS, posts)
        build.build(verbose=False)
        return self.redirect("செய்தி வெளியிடப்பட்டது: %s" % title)

    def add_ad(self, f, files):
        slot = f.get("slot")
        if slot not in dict(SLOTS):
            return self.redirect("தவறான விளம்பர இடம்", True)
        image = next((save_upload(fn, data, IMAGE_TYPES) for name, fn, data in files if name == "image_file"), None)
        image = image or f.get("image_url", "").strip()
        code = f.get("code", "").strip()
        if not image and not code:
            return self.redirect("படம் அல்லது விளம்பரக் குறியீடு தேவை", True)
        ad = {
            "id": "ad" + dt.datetime.now().strftime("%Y%m%d%H%M%S"),
            "name": f.get("name", "").strip(),
            "type": "image" if image else "html",
            "image": image,
            "link": f.get("link", "").strip(),
            "alt": f.get("name", "").strip(),
            "code": "" if image else code,
            "start": f.get("start", ""),
            "end": f.get("end", ""),
            "active": True,
        }
        ad = {k: v for k, v in ad.items() if v != ""}
        ads = load(ADS, {"slots": {}})
        ads.setdefault("slots", {}).setdefault(slot, []).append(ad)
        save(ADS, ads)
        build.build(verbose=False)
        return self.redirect("விளம்பரம் சேர்க்கப்பட்டது")


def main():
    parser = argparse.ArgumentParser(description="Local admin panel")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    build.build(verbose=False)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print("Admin panel:  http://localhost:%d/admin" % args.port)
    print("Site preview: http://localhost:%d/" % args.port)
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
