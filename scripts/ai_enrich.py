#!/usr/bin/env python3
"""Rewrite each fetched story as our own Tamil report.

Every story on the site is written here: the model reads the full article the publisher
put out and writes a fresh Tamil report from the facts in it — a new headline, a
one-line lede for the cards, and a few paragraphs of body. English sources (Ada Derana,
Newswire, The Island, Tamil Guardian, the Northern Provincial Council) are translated in
the same pass, so the whole site reads in Sri Lankan Tamil.

Nothing is invented: the rewrite may only use what the source article states. When a
story arrives with too little text to write from, the model says so and the story is
held back rather than published as a bare headline.

Two providers, chosen by "provider" in config/ai.json:

    gemini     Google's free tier. Get a key at aistudio.google.com — no card needed.
                   export GEMINI_API_KEY=...
                   pip install google-genai
    anthropic  Claude. Better Tamil, but every story costs money.
                   export ANTHROPIC_API_KEY=sk-ant-...
                   pip install anthropic

Free-tier requests are rate limited, and Google says free-tier content may be used to
improve their products. Whatever a run cannot get through is simply picked up by the
next one.

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
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE_FILE = ROOT / "data" / "fetched.json"
TEXTS_FILE = ROOT / "data" / "texts.json"
CONFIG_FILE = ROOT / "config" / "ai.json"

DEFAULTS = {
    "enabled": True,
    "provider": "gemini",
    "max_items_per_run": 40,
    "min_text_chars": 400,
    "body_paragraphs": "3-5",
    "max_attempts": 3,
    "gemini": {
        "model": "gemini-3.5-flash",
        # The free tier allows only a handful of requests a minute, so ask for few at a
        # time and leave a gap between them rather than collecting rate-limit errors.
        "concurrency": 2,
        "min_interval_seconds": 4,
        "max_tokens": 16000,
    },
    "anthropic": {
        "model": "claude-opus-5",
        "effort": "medium",
        "concurrency": 4,
        "min_interval_seconds": 0,
        "max_tokens": 16000,
    },
}


class RateLimited(Exception):
    """The provider will not take more requests for now.

    Not a failure of the story: the run stops early and the next one continues where
    this left off, so a free tier's daily allowance simply spreads across the day.
    """

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
6. மூல உரையில் "இன்று", "நேற்று", "நாளை" போன்ற சொற்கள் இருந்தால், செய்தி வெளியான
   திகதியை வைத்து அவற்றைத் தெளிவான திகதியாக எழுதுங்கள் (எ.கா. "செப்டெம்பர் 25 அன்று").
   வாசகர் இதை எப்போது வாசிப்பார் என்பது தெரியாது.
7. உரையில் செய்தி எழுதப் போதுமான தகவல் இல்லாவிட்டால் (வெறும் தலைப்பு, விளம்பரம்,
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
    """Settings for the chosen provider, flattened over the shared ones."""
    cfg = dict(DEFAULTS)
    stored = load_json(CONFIG_FILE, {})
    for key, value in stored.items():
        if isinstance(value, dict) and isinstance(cfg.get(key), dict):
            merged = dict(cfg[key])
            merged.update(value)
            cfg[key] = merged
        else:
            cfg[key] = value

    name = cfg.get("provider", "gemini")
    if name not in PROVIDERS:
        raise SystemExit("Unknown provider %r in config/ai.json. Use one of: %s"
                         % (name, ", ".join(sorted(PROVIDERS))))
    flat = {k: v for k, v in cfg.items() if not isinstance(v, dict)}
    flat.update(cfg.get(name, {}))
    flat["provider"] = name
    return flat


SL_TZ = dt.timezone(dt.timedelta(hours=5, minutes=30))
TA_MONTHS = ["ஜனவரி", "பெப்ரவரி", "மார்ச்", "ஏப்ரல்", "மே", "ஜூன்", "ஜூலை",
             "ஓகஸ்ட்", "செப்டெம்பர்", "ஒக்டோபர்", "நவம்பர்", "டிசம்பர்"]


def published_on(item):
    """The story's date in Colombo time, so 'today' in the source becomes a real date."""
    try:
        when = dt.datetime.fromisoformat(str(item.get("published", "")).replace("Z", "+00:00"))
    except ValueError:
        return "தெரியவில்லை"
    when = when.astimezone(SL_TZ)
    return "%d %s %d" % (when.day, TA_MONTHS[when.month - 1], when.year)


def prompt_for(cfg, item, text):
    language = "ஆங்கிலம்" if item.get("lang") == "en" else "தமிழ்"
    return ("மூல மொழி: %s\n"
            "செய்தி வெளியான திகதி: %s\n"
            "மூலத் தலைப்பு: %s\n\n"
            "செய்தி அறிக்கை:\n---\n%s\n---\n\n"
            "மேலுள்ள அறிக்கையிலிருந்து, %s பந்திகளில் உங்கள் சொந்த தமிழ்ச் செய்தியை எழுதுங்கள். "
            "இந்தச் செய்தி எந்தப் பிரிவுக்கு உரியது என்பதையும் தெரிவு செய்யுங்கள்."
            % (language, published_on(item), item.get("title", ""), text, cfg["body_paragraphs"]))


def parsed(raw):
    """The model's JSON, or None when it came back truncated or malformed."""
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


# ------------------------------------------------------------------ Gemini

def gemini_client(cfg):
    if not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit(
            "No GEMINI_API_KEY set — no story can be rewritten, so nothing new will be\n"
            "published. Get a free key at https://aistudio.google.com/apikey and set it as\n"
            "a GitHub repository secret (Settings > Secrets and variables > Actions).")
    try:
        from google import genai
    except ImportError:
        raise SystemExit("The 'google-genai' package is not installed. pip install google-genai")
    return genai.Client()


def gemini_rewrite(client, cfg, item, text):
    from google.genai import types, errors
    settings = {
        "system_instruction": SYSTEM,
        "response_mime_type": "application/json",
        "response_json_schema": SCHEMA,
        "max_output_tokens": cfg.get("max_tokens", 16000),
    }
    if cfg.get("thinking_budget") is not None:
        settings["thinking_config"] = types.ThinkingConfig(
            thinking_budget=int(cfg["thinking_budget"]))
    try:
        response = client.models.generate_content(
            model=cfg["model"],
            contents=prompt_for(cfg, item, text),
            config=types.GenerateContentConfig(**settings),
        )
    except errors.ClientError as e:
        # 429 is the free tier saying "not now", which is not this story's fault.
        if getattr(e, "code", None) == 429:
            raise RateLimited(str(e)[:200])
        raise
    usage = getattr(response, "usage_metadata", None)
    tokens = (getattr(usage, "prompt_token_count", 0) or 0,
              getattr(usage, "candidates_token_count", 0) or 0)
    data = parsed(getattr(response, "text", None))
    return (data, tokens) if data else None


# ------------------------------------------------------------------ Claude

def anthropic_client(cfg):
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise SystemExit(
            "No ANTHROPIC_API_KEY set — no story can be rewritten, so nothing new will be\n"
            "published. Set it as a GitHub repository secret (Settings > Secrets > Actions),\n"
            'or switch "provider" in config/ai.json to "gemini" for a free key.')
    try:
        import anthropic
    except ImportError:
        raise SystemExit("The 'anthropic' package is not installed. pip install anthropic")
    return anthropic.Anthropic()


def anthropic_rewrite(client, cfg, item, text):
    import anthropic
    try:
        response = client.messages.create(
            model=cfg["model"],
            # Thinking is on by default and counts towards this, so leave room: a reply
            # cut off mid-JSON is unparseable and the story is paid for and thrown away.
            max_tokens=cfg.get("max_tokens", 16000),
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt_for(cfg, item, text)}],
            output_config={
                "effort": cfg.get("effort", "medium"),
                "format": {"type": "json_schema", "schema": SCHEMA},
            },
        )
    except anthropic.RateLimitError as e:
        raise RateLimited(str(e)[:200])
    if response.stop_reason in ("refusal", "max_tokens"):
        return None
    raw = next((b.text for b in response.content if b.type == "text"), "")
    data = parsed(raw)
    if not data:
        return None
    return data, (response.usage.input_tokens, response.usage.output_tokens)


PROVIDERS = {
    "gemini": (gemini_client, gemini_rewrite),
    "anthropic": (anthropic_client, anthropic_rewrite),
}

# Which environment variable each provider needs, for the pre-flight check.
KEY_FOR = {"gemini": ("GEMINI_API_KEY",),
           "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}


def key_present(cfg):
    return any(os.environ.get(name) for name in KEY_FOR[cfg["provider"]])


def available_models(cfg):
    """Model names the provider will accept, or None when we cannot ask.

    Model names move: a name that was right when this was written may not be a year
    later. Checking once before a run turns a confusing mid-run error into a clear one.
    """
    try:
        if cfg["provider"] == "gemini":
            from google import genai
            return sorted(m.name.split("/")[-1] for m in genai.Client().models.list())
        import anthropic
        return sorted(m.id for m in anthropic.Anthropic().models.list(limit=100))
    except Exception:
        return None


def rewrite(client, cfg, item, text):
    """One rewritten story as (data, (input_tokens, output_tokens)).

    None means the model declined or answered with something that was not usable JSON.
    """
    return PROVIDERS[cfg["provider"]][1](client, cfg, item, text)


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
    item.pop("ai_fails", None)
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
        # Repeatedly failed: stop paying for the same error every half hour.
        if not redo and item.get("ai_fails", 0) >= cfg.get("max_attempts", 3):
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
        print("Would rewrite %d stories with %s (%s):"
              % (len(todo), cfg["model"], cfg["provider"]))
        for item, text in todo[:5]:
            print("  %-12s %-4s %5d chars  %s" % (item["id"], item.get("lang"), len(text),
                                                  item["title"][:60]))
        return len(todo)
    if not todo:
        return 0

    client = PROVIDERS[cfg["provider"]][0](cfg)
    done = thin = failed = 0
    in_tok = out_tok = 0
    stopped = None

    # A free tier counts requests per minute, so hold a minimum gap between them.
    gap = float(cfg.get("min_interval_seconds", 0) or 0)
    pace = threading.Lock()
    last = [0.0]

    def work(pair):
        item, text = pair
        if gap:
            with pace:
                wait = gap - (time.time() - last[0])
                if wait > 0:
                    time.sleep(wait)
                last[0] = time.time()
        try:
            return item, rewrite(client, cfg, item, text), len(text), None
        except Exception as e:
            return item, None, len(text), e

    workers = max(1, int(cfg.get("concurrency", 2)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for item, result, chars, error in pool.map(work, todo):
            if isinstance(error, RateLimited):
                # Not this story's fault, so no attempt is recorded against it.
                stopped = error
                continue
            if error is not None:
                # Record the attempt so a story that fails the same way every time backs
                # off instead of being retried on every run until it ages out.
                item["ai_fails"] = item.get("ai_fails", 0) + 1
                failed += 1
                print("  rewrite failed for %s (attempt %d): %s"
                      % (item["id"], item["ai_fails"], error))
                continue
            if result is None:  # declined, truncated, or not usable JSON
                item["ai_thin"] = True
                item["ai_thin_chars"] = chars
                thin += 1
                continue
            data, (used_in, used_out) = result
            in_tok += used_in
            out_tok += used_out
            if apply(item, data, cfg, chars):
                done += 1
            else:
                thin += 1

    save_json(STORE_FILE, store)
    if not quiet or done:
        print("Tamil rewrites (%s): %d written, %d held as too thin, %d failed "
              "(%d input / %d output tokens)"
              % (cfg["provider"], done, thin, failed, in_tok, out_tok))
    if stopped is not None:
        print("Rate limit reached, so the rest waits for the next run: %s" % stopped)
    return done


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--redo", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="list the work without calling the API")
    parser.add_argument("--check", action="store_true",
                        help="report the provider and whether its key is set, then exit")
    parser.add_argument("--no-build", action="store_true")
    args = parser.parse_args()
    if args.check:
        cfg = config()
        ok = key_present(cfg)
        wanted = " or ".join(KEY_FOR[cfg["provider"]])
        print("provider: %s (%s)" % (cfg["provider"], cfg["model"]))
        print("%s: %s" % (wanted, "set" if ok else "NOT SET"))
        if not ok:
            print("Stories are rewritten in Tamil before they are published, so without "
                  "this key nothing new can go live.")
            if cfg["provider"] == "gemini":
                print("Get a free key at https://aistudio.google.com/apikey — no card needed.")
            return 1
        names = available_models(cfg)
        if names is not None and cfg["model"] not in names:
            near = [n for n in names if "flash" in n or "haiku" in n or "sonnet" in n]
            print("model %r is not one this key can use." % cfg["model"])
            print("Available, lighter ones first: %s" % ", ".join((near or names)[:12]))
            print('Set it under "%s" in config/ai.json.' % cfg["provider"])
            return 1
        if names is not None:
            print("model %s is available." % cfg["model"])
        return 0
    enrich(limit=args.limit, redo=args.redo, dry_run=args.dry_run)
    if not args.no_build and not args.dry_run:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import build
        try:
            build.build()
        except build.SiteNotReady as why:
            print("REFUSING TO BUILD: %s" % why)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
