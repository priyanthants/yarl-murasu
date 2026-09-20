#!/usr/bin/env python3
"""Write a short Tamil summary for each fetched story, in our own words.

For English stories (Northern Provincial Council, Tamil Guardian) it also translates
the headline, so the whole site reads in Tamil.

The summary is written only from the excerpt the publisher syndicates; nothing is
invented, and stories with too little text are left alone (headline + source link only).

Needs an Anthropic API key:
    export ANTHROPIC_API_KEY=sk-ant-...
and the SDK:  python3 -m pip install anthropic     (Python 3.10+)

Usage:
    python3 scripts/ai_enrich.py            # summarise anything not done yet
    python3 scripts/ai_enrich.py --limit 20
    python3 scripts/ai_enrich.py --redo     # redo stories already summarised
"""
import argparse
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
    "max_items_per_run": 40,
    "min_text_chars": 180,
    "summary_sentences": "3-4",
}

SYSTEM = """நீங்கள் யாழ்ப்பாணத்தைச் சேர்ந்த ஒரு தமிழ் செய்தி ஆசிரியர்.

உங்கள் வேலை: கொடுக்கப்பட்ட செய்திப் பகுதியிலிருந்து, உங்கள் சொந்த வார்த்தைகளில் ஒரு சுருக்கத்தை எழுதுவது.

விதிகள்:
- கொடுக்கப்பட்ட உரையில் உள்ள தகவல்களை மட்டுமே பயன்படுத்துங்கள். எதையும் கற்பனை செய்யவோ, சேர்க்கவோ கூடாது.
- மூல உரையை அப்படியே நகலெடுக்காதீர்கள் — உங்கள் சொந்த நடையில் மீண்டும் எழுதுங்கள்.
- எளிய, தெளிவான இலங்கைத் தமிழ் நடை. செய்தித்தாள் பாணி. கருத்து தெரிவிக்க வேண்டாம்.
- உரை மிகக் குறைவாக இருந்தால் அல்லது சுருக்கம் எழுத போதுமான தகவல் இல்லாவிட்டால், summary ஐ காலியாக ("") விடுங்கள்.
- ஆங்கிலச் செய்தியாக இருந்தால், தலைப்பையும் தமிழில் மொழிபெயர்த்துத் தாருங்கள்; தமிழ்ச் செய்தியாக இருந்தால் title_ta ஐ காலியாக விடுங்கள்."""

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "Tamil summary in your own words, or \"\" if not enough text"},
        "title_ta": {"type": "string", "description": "Tamil headline when the source is English, else \"\""},
    },
    "required": ["summary", "title_ta"],
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


def summarise(client, cfg, item, text):
    prompt = "மூலம்: %s\nதலைப்பு: %s\n\nசெய்திப் பகுதி:\n%s\n\n%s வாக்கியங்களில் தமிழ்ச் சுருக்கம் எழுதுங்கள்." % (
        item.get("source", ""), item["title"], text, cfg["summary_sentences"])
    response = client.messages.create(
        model=cfg["model"],
        max_tokens=2000,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )
    if response.stop_reason == "refusal":
        return None
    raw = next((b.text for b in response.content if b.type == "text"), "")
    data = json.loads(raw)
    return data, response.usage


def enrich(limit=None, redo=False, quiet=False):
    cfg = config()
    if not cfg.get("enabled", True):
        return 0
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        if not quiet:
            print("No ANTHROPIC_API_KEY set — skipping Tamil summaries.")
        return 0
    try:
        import anthropic
    except ImportError:
        if not quiet:
            print("The 'anthropic' package is not installed — skipping Tamil summaries.")
        return 0

    store = load_json(STORE_FILE, {"items": []})
    texts = load_json(TEXTS_FILE, {})
    items = store.get("items", [])
    todo = [i for i in items
            if (redo or not i.get("ai_summary"))
            and len(texts.get(i["id"], "") or i.get("summary", "")) >= cfg["min_text_chars"]]
    todo = todo[: (limit or cfg["max_items_per_run"])]
    if not todo:
        return 0

    client = anthropic.Anthropic()
    done, in_tok, out_tok = 0, 0, 0
    for item in todo:
        text = texts.get(item["id"]) or item.get("summary", "")
        try:
            result = summarise(client, cfg, item, text[:6000])
        except Exception as e:
            print("  AI failed for %s: %s" % (item["id"], e))
            continue
        if not result:
            continue
        data, usage = result
        in_tok += usage.input_tokens
        out_tok += usage.output_tokens
        summary = (data.get("summary") or "").strip()
        if summary:
            item["ai_summary"] = summary
            item["ai_model"] = cfg["model"]
            item["ai_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
            done += 1
        title_ta = (data.get("title_ta") or "").strip()
        if title_ta and item.get("lang") == "en":
            item["title_ta"] = title_ta

    save_json(STORE_FILE, store)
    if not quiet or done:
        print("Tamil summaries written: %d of %d tried (%d input / %d output tokens)"
              % (done, len(todo), in_tok, out_tok))
    return done


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--redo", action="store_true")
    parser.add_argument("--no-build", action="store_true")
    args = parser.parse_args()
    enrich(limit=args.limit, redo=args.redo)
    if not args.no_build:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import build
        build.build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
