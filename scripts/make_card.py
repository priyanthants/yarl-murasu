#!/usr/bin/env python3
"""Make a shareable image of the day's main news (for Instagram, Facebook or WhatsApp).

Renders a branded card with the top headlines and saves it as a PNG in site/cards/.

Usage:
    python3 scripts/make_card.py                     # today, square 1080x1080
    python3 scripts/make_card.py --size portrait     # 1080x1350 (fills more of the feed)
    python3 scripts/make_card.py --size story        # 1080x1920 (Instagram/WhatsApp story)
    python3 scripts/make_card.py --count 4 --category jaffna
    python3 scripts/make_card.py --id p20260920... # one single story
"""
import argparse
import datetime as dt
import json
import shutil
import subprocess
import time
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
CARDS = SITE / "cards"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402

SIZES = {"square": (1080, 1080), "portrait": (1080, 1350), "story": (1080, 1920)}
# how many stories comfortably fit on each shape
FITS = {"square": 4, "portrait": 5, "story": 7}
CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
]


def find_chrome(explicit=None):
    for candidate in ([explicit] if explicit else []) + CHROME_CANDIDATES:
        if candidate and (Path(candidate).exists() or shutil.which(candidate)):
            return candidate
    raise SystemExit("Google Chrome was not found — install it, or pass --chrome /path/to/chrome")


def pick_items(site, count, category=None, item_id=None, day=None):
    items = [build.display(i) for i in build.collect_items(site)]
    if item_id:
        chosen = [i for i in items if i["id"] == item_id]
        if not chosen:
            raise SystemExit("No story with id %s" % item_id)
        return chosen
    day = day or dt.datetime.now(build.SL_TZ).date()
    today = [i for i in items if build.parse_date(i["published"]).astimezone(build.SL_TZ).date() == day]
    pool = today or items
    if category:
        pool = [i for i in pool if i.get("category") == category or category in i.get("tags", [])] or pool
    own = [i for i in pool if i.get("type") == "local" or i.get("breaking")]
    local_news = [i for i in pool if i.get("category") == "jaffna" and i not in own]
    rest = [i for i in pool if i not in own and i not in local_news]
    ordered, seen = [], set()
    for i in own + local_news + rest:
        if i["id"] not in seen:
            seen.add(i["id"])
            ordered.append(i)
    return ordered[:count]


def card_html(site, items, width, height, day):
    cats = {c["id"]: c for c in site["categories"]}
    single = len(items) == 1
    esc = build.esc
    rows = []
    for n, item in enumerate(items, 1):
        cat = cats.get(item.get("category"), {"name": "செய்தி", "color": "#8b1e1e"})
        image = item.get("image") or (item.get("images") or [None])[0]
        rows.append("""
      <article class="story{single}">
        {picture}
        <div class="story-text">
          <span class="chip" style="background:{color}">{cat}</span>
          <h2>{title}</h2>
          {summary}
          <span class="src">{source}</span>
        </div>
        {num}
      </article>""".format(
            single=" single" if single else "",
            picture=('<div class="pic" style="background-image:url(\'%s\')"></div>' % esc(image)) if image else "",
            color=cat["color"], cat=esc(cat["name"]), title=esc(item["title"]),
            summary=('<p>%s</p>' % esc(item["summary"][:260])) if single and item.get("summary") else "",
            source=esc(item.get("source", "")),
            num="" if single else '<span class="num">%02d</span>' % n))

    return """<!doctype html><html lang="ta"><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Tamil:wght@500;600;700&family=Noto+Serif+Tamil:wght@700;800&display=swap" rel="stylesheet">
<style>
  *{{box-sizing:border-box;margin:0}}
  body{{width:{w}px;height:{h}px;overflow:hidden;font-family:"Noto Sans Tamil",sans-serif;
    background:linear-gradient(160deg,#5c1111,#8b1e1e 45%,#a83a22);color:#fff;display:flex;flex-direction:column}}
  .sheet{{position:absolute;inset:0;background:url('../assets/img/palm.svg') right -60px bottom -40px/auto 75% no-repeat;opacity:.5}}
  header{{position:relative;display:flex;align-items:center;gap:22px;padding:38px 52px 20px}}
  header img{{width:96px;height:96px}}
  .name{{font-family:"Noto Serif Tamil",serif;font-weight:800;font-size:52px;line-height:1.2}}
  .date{{font-size:24px;opacity:.88;margin-top:6px;white-space:nowrap}}
  .kicker{{margin-left:auto;text-align:right;font-weight:700;font-size:22px;background:rgba(255,255,255,.16);
    padding:10px 20px;border-radius:999px;max-width:250px}}
  main{{position:relative;flex:1;min-height:0;display:flex;flex-direction:column;gap:{gap}px;
    padding:6px 52px 26px;justify-content:center;overflow:hidden}}
  .story{{position:relative;flex:1 1 0;min-height:0;overflow:hidden;display:flex;align-items:center;gap:24px;background:rgba(255,255,255,.97);color:#1d1714;
    border-radius:22px;padding:{pad}px 28px;box-shadow:0 12px 30px rgba(0,0,0,.25)}}
  .story .pic{{width:{picw}px;height:min({picw2}px,82%);flex:none;border-radius:16px;background-size:cover;background-position:center}}
  .story-text{{flex:1;min-width:0}}
  .chip{{display:inline-block;color:#fff;font-weight:700;font-size:19px;padding:2px 15px;border-radius:999px;margin-bottom:8px}}
  .story h2{{font-family:"Noto Serif Tamil",serif;font-weight:800;font-size:{title}px;line-height:1.45;
    display:-webkit-box;-webkit-line-clamp:{lines};-webkit-box-orient:vertical;overflow:hidden}}
  .src{{display:block;margin-top:8px;font-size:19px;color:#7a6e64;font-weight:600}}
  .num{{position:absolute;top:-14px;right:22px;font-family:"Noto Serif Tamil",serif;font-weight:800;font-size:40px;
    color:#e0a526;background:#5c1111;border-radius:50%;width:70px;height:70px;display:grid;place-items:center;
    box-shadow:0 6px 16px rgba(0,0,0,.3)}}
  .story.single{{flex:1 1 auto;flex-direction:column;align-items:stretch;gap:22px;padding:34px}}
  .story.single .pic{{width:100%;height:{pich}px}}
  .story.single h2{{font-size:56px;-webkit-line-clamp:4}}
  .story.single p{{margin-top:16px;font-size:28px;line-height:1.75;color:#4a403a;
    display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}}
  footer{{position:relative;display:flex;align-items:center;justify-content:space-between;gap:16px;
    padding:14px 52px 34px;font-size:22px;font-weight:600}}
  footer span:first-child{{opacity:.9;font-size:20px}}
  footer .site{{background:#e0a526;color:#3a0d0d;padding:10px 24px;border-radius:999px;font-weight:700;
    white-space:nowrap;font-size:21px}}
</style></head><body>
<div class="sheet"></div>
<header>
  <img src="../assets/img/logo.svg" alt="">
  <div><div class="name">{site_name}</div><div class="date">{date}</div></div>
  <div class="kicker">இன்றைய முக்கியச் செய்திகள்</div>
</header>
<main>{rows}</main>
<footer><span>{tagline}</span><span class="site">{url}</span></footer>
</body></html>""".format(
        w=width, h=height, gap=18 if len(items) > 3 else 26,
        title=31 if len(items) > 3 else 38, pich=440 if height > 1200 else 330,
        lines=2 if len(items) > 3 else 3, pad=18 if len(items) > 3 else 26, picw=150 if len(items) > 3 else 172,
        picw2=114 if len(items) > 3 else 132,
        site_name=esc(site["name"]), date=build.tamil_date(dt.datetime.combine(day, dt.time(9)), with_time=False),
        tagline=esc(site.get("tagline", "")), rows="".join(rows),
        url=esc((site.get("site_url") or "").replace("https://", "").rstrip("/") or site.get("name_en", "")))


def render(html_path, out_path, width, height, chrome):
    """Screenshot the card with headless Chrome.

    Chrome sometimes keeps running after writing the file, so wait for the image
    to appear and then stop the process instead of waiting for it to exit.
    """
    tmp_profile = CARDS / "_chrome"
    if out_path.exists():
        out_path.unlink()
    cmd = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-sandbox",
           "--user-data-dir=%s" % tmp_profile, "--window-size=%d,%d" % (width, height),
           "--virtual-time-budget=6000", "--timeout=10000",
           "--screenshot=%s" % out_path, str(html_path)]
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 90
    while time.time() < deadline:
        if out_path.exists() and out_path.stat().st_size > 0 and process.poll() is None:
            time.sleep(1.5)  # let the file finish writing
            break
        if process.poll() is not None:
            break
        time.sleep(0.5)
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    shutil.rmtree(tmp_profile, ignore_errors=True)
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise SystemExit("Chrome did not produce an image")


def prune(keep_days=14):
    cutoff = dt.date.today() - dt.timedelta(days=keep_days)
    for f in CARDS.glob("*.png"):
        stamp = f.name[:10]
        try:
            if dt.date.fromisoformat(stamp) < cutoff:
                f.unlink()
        except ValueError:
            continue


def make(count=5, size="square", category=None, item_id=None, chrome=None, out=None, skip_existing=False):
    site = build.load_json(ROOT / "config" / "site.json", None)
    width, height = SIZES[size]
    day = dt.datetime.now(build.SL_TZ).date()
    items = pick_items(site, min(count, FITS[size]), category, item_id, day)
    if not items:
        raise SystemExit("No stories to put on the card yet")
    CARDS.mkdir(parents=True, exist_ok=True)
    prune()
    html_path = CARDS / "_card.html"
    html_path.write_text(card_html(site, items, width, height, day), encoding="utf-8")
    name = out or "%s-%s%s.png" % (day.isoformat(), size, "-" + item_id if item_id else "")
    out_path = CARDS / name
    if skip_existing and out_path.exists():
        print("Card already made for today: %s" % out_path)
        return out_path
    render(html_path, out_path, width, height, find_chrome(chrome))
    html_path.unlink(missing_ok=True)
    print("Card ready: %s (%d stories)" % (out_path, len(items)))
    return out_path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=99, help="how many stories (capped to what fits)")
    parser.add_argument("--size", choices=list(SIZES), default="square")
    parser.add_argument("--category")
    parser.add_argument("--id", dest="item_id")
    parser.add_argument("--chrome")
    parser.add_argument("--out")
    parser.add_argument("--skip-existing", action="store_true",
                        help="do nothing if today's card was already made")
    args = parser.parse_args()
    make(args.count, args.size, args.category, args.item_id, args.chrome, args.out, args.skip_existing)
    return 0


if __name__ == "__main__":
    sys.exit(main())
