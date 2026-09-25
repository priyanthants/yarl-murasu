#!/usr/bin/env python3
"""Rewrite each fetched story as our own Tamil report.

Every story on the site is written here: Claude reads the full article the publisher
put out, and writes a fresh Tamil report from the facts in it — a new headline, a
one-line lede for the cards, and a few paragraphs of body. English sources (Ada Derana,
Tamil Guardian, the Northern Provincial Council) are translated in the same pass, so
the whole site reads in Sri Lankan Tamil.

Nothing is invented: the rewrite may only use what the source article states. When a
story arrives with too little text to write from, the model says so and the story is
held back rather than published as a bare headline.

Needs an Anthropic API key:
    export ANTHROPIC_API_KEY=sk-ant-...
and the SDK:  python3 -m pip install anthropic     (Python 3.10+)

Usage:
    python3 scripts/ai_enrich.py            # rewrite anything not done yet
    python3 scripts/ai_enrich.py --limit 20
    python3 scripts/ai_enrich.py --redo     # rewrite stories already done
    python3 scripts/ai_enrich.py --dry-run  # show what would be sent, call nothing
"""
import argparse
import concurrent.futures
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE_FILE = ROOT / "data" / "fetched.json"
TEXTS_FILE = ROOT / "data" / "texts.json"
CONFIG_FILE = ROOT / "config" / "ai.json"

DEFAULTS = {
    "enabled": True,
    "model": "claude-opus-5",
    "effort": "medium",
    "max_items_per_run": 40,
    "min_text_chars": 400,
    "body_paragraphs": "3-5",
    "concurrency": 4,
}

SYSTEM = """நீங்கள் யாழ்ப்பாணத்திலிருந்து வெளிவரும் "யாழ் முரசு" தமிழ்ச் செய்தித் தளத்தின் ஆசிரியர்.

உங்கள் வேலை: கொடுக்கப்பட்ட செய்தி அறிக்கையை வாசித்து, அதிலுள்ள தகவல்களைக் கொண்டு
**உங்கள் சொந்த வார்த்தைகளில் ஒரு புதிய தமிழ்ச் செய்தியை** எழுதுவது.

விதிகள்:
1. கொடுக்கப்பட்ட உரையில் உள்ள தகவல்களை மட்டுமே பயன்படுத்துங்கள். எந்தத் தகவலையும்,
   பெயரையும், எண்ணையும், திகதியையும் கற்பனை செய்யவோ சேர்க்கவோ கூடாது.
2. மூல உரையின் வாக்கியங்களை நகலெடுக்கவோ, சிறிது மாற்றி எழுதவோ கூடாது. செய்தியை
   முழுமையாகப் புரிந்துகொண்டு, புதிதாக உங்கள் நடையில் எழுதுங்கள். தலைப்பும் புதியதாக இருக்க வேண்டும்.
3. மூல உரை ஆங்கிலத்தில் இருந்தாலும், நீங்கள் எழுதுவது முழுக்க முழுக்க இலங்கைத் தமிழில்
   இருக்க வேண்டும். ஆள்பெயர், இடப்பெயர், நிறுவனப் பெயர்களைத் தமிழில் எழுதுங்கள்.
4. எளிய, தெளிவான, செய்தித்தாள் நடை. முதல் பந்தியில் மிக முக்கியமான தகவல். கருத்து
   தெரிவிக்கவோ, மிகைப்படுத்தவோ கூடாது.
5. மூல ஊடகத்தின் பெயரை எழுதாதீர்கள். "இந்தச் செய்தியின்படி", "அறிக்கையில்" போன்ற
   சொற்றொடர்களைத் தவிர்த்து, நேரடியாகச் செய்தியை எழுதுங்கள்.
6. உரையில் செய்தி எழுதப் போதுமான தகவல் இல்லாவிட்டால் (வெறும் தலைப்பு, விளம்பரம்,
   அல்லது ஒன்றிரண்டு வரிகள் மட்டும்), enough_material ஐ false ஆக்கி மற்ற புலங்களைக்
   காலியாக விடுங்கள். அரைகுறைச் செய்தி எழுத வேண்டாம்."""

SCHEMA = {
    "type": "object",
    "properties": {
        "enough_material": {
            "type": "boolean",
            "description": "true only when the source text holds a real, reportable story",
        },
        "headline": {
            "type": "string",
            "description": "A fresh Tamil headline in our own wording, 6-14 words, no publisher name",
        },
        "lede": {
            "type": "string",
            "description": "One or two Tamil sentences summarising the story, for the card on the home page",
        },
        "body": {
            "type": "array",
            "items": {"type": "string"},
            "description": "The Tamil report, one string per paragraph, written from the facts only",
        },
        "category": {
            "type": "string",
            "enum": ["jaffna", "srilanka", "world", "sports"],
            "description": ("Which section the story belongs in: jaffna for the Northern "
                            "Province (Jaffna, Kilinochchi, Mullaitivu, Vavuniya, Mannar), "
                            "srilanka for the rest of the country, world for everywhere else, "
                            "sports for sport wherever it happens"),
        },
    },
    "required": ["enough_material", "headline", "lede", "body", "category"],
    "additionalProperties": False,
}


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save_json(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def config():
    cfg = dict(DEFAULTS)
    cfg.update(load_json(CONFIG_FILE, {}))
    return cfg


def prompt_for(cfg, item, text):
    language = "ஆங்கிலம்" if item.get("lang") == "en" else "தமிழ்"
    return ("மூல மொழி: %s\n"
            "மூலத் தலைப்பு: %s\n\n"
            "செய்தி அறிக்கை:\n---\n%s\n---\n\n"
            "மேலுள்ள அறிக்கையிலிருந்து, %s பந்திகளில் உங்கள் சொந்த தமிழ்ச் செய்தியை எழுதுங்கள். "
            "இந்தச் செய்தி எந்தப் பிரிவுக்கு உரியது என்பதையும் தெரிவு செய்யுங்கள்."
            % (language, item.get("title", ""), text, cfg["body_paragraphs"]))


def rewrite(client, cfg, item, text):
    """Ask Claude for one rewritten story. Returns (data, usage) or None."""
    response = client.messages.create(
        model=cfg["model"],
        max_tokens=8000,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt_for(cfg, item, text)}],
        output_config={
            "effort": cfg.get("effort", "medium"),
            "format": {"type": "json_schema", "schema": SCHEMA},
        },
    )
    if response.stop_reason == "refusal":
        return None
    raw = next((b.text for b in response.content if b.type == "text"), "")
    return json.loads(raw), response.usage


def apply(item, data, cfg, text_chars=0):
    """Store a rewrite on the item. Returns True when the story is now publishable."""
    headline = (data.get("headline") or "").strip()
    lede = (data.get("lede") or "").strip()
    body = [p.strip() for p in (data.get("body") or []) if p and p.strip()]
    if not data.get("enough_material") or not headline or not body:
        item["ai_thin"] = True
        item["ai_thin_chars"] = text_chars
        return False
    item["ai_title"] = headline
    item["title_ta"] = headline
    item["ai_summary"] = lede or body[0][:200]
    item["ai_body"] = body
    # Keyword matching files stories by the words in a headline; the rewrite has read the
    # whole report, so its judgement of which section a story belongs in is the better one.
    category = (data.get("category") or "").strip()
    if category in ("jaffna", "srilanka", "world", "sports"):
        item["category"] = category
        if category not in item.get("tags", []):
            item["tags"] = [category] + [t for t in item.get("tags", []) if t != category]
    item["ai_model"] = cfg["model"]
    item["ai_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    item.pop("ai_thin", None)
    item.pop("ai_thin_chars", None)
    return True


def source_text(item, texts, cfg):
    """The material a rewrite is written from: the article page, else the feed teaser."""
    text = texts.get(item["id"], "")
    if len(text) < len(item.get("summary", "")):
        text = item.get("summary", "")
    return text[:12000]


def pending(items, texts, cfg, redo=False):
    todo = []
    for item in items:
        if item.get("type") == "local":
            continue
        if not redo and item.get("ai_body"):
            continue
        text = source_text(item, texts, cfg)
        if len(text) < cfg["min_text_chars"]:
            continue  # nothing to write from; fetch_news will try the page again
        # Already judged too thin to report. Only pay for it again if the article page
        # has since given us materially more to work with.
        if not redo and item.get("ai_thin") and len(text) <= item.get("ai_thin_chars", 0):
            continue
        todo.append((item, text))
    return todo


def enrich(limit=None, redo=False, quiet=False, dry_run=False):
    cfg = config()
    if not cfg.get("enabled", True):
        return 0
    store = load_json(STORE_FILE, {"items": []})
    texts = load_json(TEXTS_FILE, {})
    todo = pending(store.get("items", []), texts, cfg, redo)[: (limit or cfg["max_items_per_run"])]

    if dry_run:
        print("Would rewrite %d stories with %s (effort %s):"
              % (len(todo), cfg["model"], cfg.get("effort")))
        for item, text in todo[:5]:
            print("  %-12s %-4s %5d chars  %s" % (item["id"], item.get("lang"), len(text),
                                                  item["title"][:60]))
        return len(todo)

    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        print("NO ANTHROPIC_API_KEY — no story can be rewritten, so nothing new will be published.")
        print("Set it as a GitHub repository secret (Settings > Secrets > Actions).")
        return 0
    try:
        import anthropic
    except ImportError:
        print("The 'anthropic' package is not installed — skipping the Tamil rewrite.")
        return 0
    if not todo:
        return 0

    client = anthropic.Anthropic()
    done = thin = failed = 0
    in_tok = out_tok = 0

    def work(pair):
        item, text = pair
        try:
            return item, rewrite(client, cfg, item, text), len(text), None
        except Exception as e:
            return item, None, len(text), e

    workers = max(1, int(cfg.get("concurrency", 4)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for item, result, chars, error in pool.map(work, todo):
            if error is not None:
                failed += 1
                print("  rewrite failed for %s: %s" % (item["id"], error))
                continue
            if result is None:  # the model declined the request; do not pay for it again
                item["ai_thin"] = True
                item["ai_thin_chars"] = chars
                thin += 1
                continue
            data, usage = result
            in_tok += usage.input_tokens
            out_tok += usage.output_tokens
            if apply(item, data, cfg, chars):
                done += 1
            else:
                thin += 1

    save_json(STORE_FILE, store)
    if not quiet or done:
        print("Tamil rewrites: %d written, %d held as too thin, %d failed "
              "(%d input / %d output tokens)" % (done, thin, failed, in_tok, out_tok))
    return done


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--redo", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="list the work without calling the API")
    parser.add_argument("--no-build", action="store_true")
    args = parser.parse_args()
    enrich(limit=args.limit, redo=args.redo, dry_run=args.dry_run)
    if not args.no_build and not args.dry_run:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import build
        build.build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
