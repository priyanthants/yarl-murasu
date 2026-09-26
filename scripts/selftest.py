#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check the publishing rules still hold, without calling the API or touching the site.

The rule this guards is the one that matters: everything a reader sees is our own Tamil
writing, and no publisher is named anywhere in the output. A stubbed rewrite stands in
for the API, so this runs offline and for free.

    python3 scripts/selftest.py

Exit status is 0 when every check passes, 1 otherwise.
"""
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

PUBLISHERS = ["வீரகேசரி", "BBC", "Ada Derana", "Tamil Guardian", "Newswire", "The Island",
              "அத தெரண", "வட மாகாண சபை", "அரச செய்திச் சேவை"]

TOWNS = ["வவுனியா", "கிளிநொச்சி", "முல்லைத்தீவு", "மன்னார்", "யாழ்ப்பாணம்", "பருத்தித்துறை",
         "சாவகச்சேரி", "நல்லூர்", "காரைநகர்", "தெல்லிப்பழை"]
SUBJECTS = ["நீர் விநியோகம்", "பாடசாலைக் கட்டிடம்", "மீன்பிடித் துறைமுகம்", "வைத்தியசாலை",
            "வீதி அபிவிருத்தி", "மின்சார இணைப்பு", "விவசாய நிலம்", "நூலகம்", "பேருந்துச் சேவை",
            "தொழில் பயிற்சி", "குடியிருப்புத் திட்டம்", "பாலம்", "சந்தை", "விளையாட்டு மைதானம்"]

failures = []


def _refuses_over_budget(ai_enrich):
    """The translator must stop at its character budget rather than spend the day's."""
    t = ai_enrich.Translator({"max_chars_per_run": 50})
    try:
        t.phrase("x" * 100, "en|ta")
    except ai_enrich.RateLimited:
        return True
    except Exception:
        return False
    return False


def check(name, ok, detail=""):
    print("%-44s %s%s" % (name, "ok" if ok else "FAILED", (" — " + detail) if detail and not ok else ""))
    if not ok:
        failures.append(name)


TOKENS = (1200, 600)   # what a provider reports back: (input, output)


def run():
    import ai_enrich
    import build

    # --- rules that need no data ------------------------------------------------
    mk = lambda t, ty="auto": {"ai_title": t, "title": t, "id": t[:8], "type": ty}
    same_event = build.drop_repeats([
        mk("ஜனாதிபதி அநுர குமார திசாநாயக்க நாளை இந்தியா பயணம்"),
        mk("ஜனாதிபதி அநுர குமார இந்தியா பயணம் நாளை ஆரம்பம்")])
    check("one story per event", len(same_event) == 1)

    same_name = build.drop_repeats([
        mk("ஜனாதிபதி அநுர குமார இந்தியா பயணம்"),
        mk("ஜனாதிபதி அநுர குமார வரவுசெலவுத் திட்டம் சமர்ப்பிப்பு")])
    check("two stories sharing a name both kept", len(same_name) == 2)

    own = build.drop_repeats([mk("யாழ்ப்பாணத்தில் புதிய மருத்துவமனை திறப்பு"),
                              mk("யாழ்ப்பாணத்தில் புதிய மருத்துவமனை திறப்பு", "local")])
    check("an own post is never a wire duplicate", len(own) == 2)

    check("a story without a rewrite is held",
          bool(build.hold_reason({"type": "auto", "title": "Something"})))
    check("a rewritten story is publishable",
          not build.hold_reason({"type": "auto", "ai_title": "வவுனியாவில் புதிய நீர்த் திட்டம்",
                                 "ai_body": ["ஒரு பந்தி."]}))
    check("an own post is always publishable", not build.hold_reason({"type": "local"}))

    # Both providers have to stay configured: switching between them is a one-word edit
    # in config/ai.json, and a broken one would only show up at the next scheduled run.
    import ai_enrich as _ai
    stored = json.loads((ROOT / "config" / "ai.json").read_text(encoding="utf-8"))
    # "auto" must land on a real provider whether or not a key happens to be present.
    saved = {k: os.environ.pop(k, None) for k in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY",
                                                  "ANTHROPIC_AUTH_TOKEN")}
    try:
        check("auto falls back to a keyless provider",
              _ai.resolve_provider("auto") == "translate")
        os.environ["GEMINI_API_KEY"] = "selftest"
        check("auto prefers a model when a key is present",
              _ai.resolve_provider("auto") == "gemini")
    finally:
        os.environ.pop("GEMINI_API_KEY", None)
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v

    for name in ("gemini", "anthropic", "translate"):
        stored["provider"] = name
        resolved = dict(_ai.DEFAULTS)
        for key, value in stored.items():
            if isinstance(value, dict) and isinstance(resolved.get(key), dict):
                merged = dict(resolved[key]); merged.update(value); resolved[key] = merged
            else:
                resolved[key] = value
        settings = {k: v for k, v in resolved.items() if not isinstance(v, dict)}
        settings.update(resolved.get(name, {}))
        check("the %s provider is configured" % name,
              bool(settings.get("model")) and name in _ai.PROVIDERS,
              "model=%r" % settings.get("model"))

    # The translation provider talks to a service that caps each request, so its
    # chunking must never hand over a piece larger than that ceiling.
    long_tamil = ("சீரற்ற வானிலை காரணமாக நுவரெலியா கல்வி வலயத்தில் நாளை பாடசாலைகளை "
                  "நடத்துவதில் சிரமம் காணப்படுமாயின், அது குறித்துத் தீர்மானிக்கும் "
                  "அதிகாரத்தை வலயக் கல்விப் பணிப்பாளர் வழங்கியுள்ளார். ") * 5
    pieces = _ai.chunks(long_tamil)
    check("translation requests stay under the size limit",
          pieces and all(len(x.encode("utf-8")) <= _ai.MM_MAX_BYTES for x in pieces),
          "largest %d bytes" % max(len(x.encode("utf-8")) for x in pieces))
    check("chunking loses no text",
          abs(len(" ".join(pieces)) - len(long_tamil.strip())) <= 10)
    check("text that came back in the wrong language is rejected",
          _ai.mostly_tamil("சீரற்ற வானிலை காரணமாக பாடசாலைகள் மூடப்பட்டன")
          and not _ai.mostly_tamil("Schools were closed because of heavy rain")
          and not _ai.mostly_tamil(""))
    check("a run cannot exceed its translation budget",
          _refuses_over_budget(_ai))

    # Both keyless/free providers must keep a gap between requests, or a run spends its
    # per-minute allowance in the first second and collects rate-limit errors instead.
    live = json.loads((ROOT / "config" / "ai.json").read_text(encoding="utf-8"))
    check("every provider has a wall-clock bound",
          all(float(json.loads((ROOT / "config" / "ai.json").read_text(encoding="utf-8"))
                    .get(n, {}).get("max_seconds", _ai.DEFAULTS["max_seconds"])) <= 900
              for n in ("gemini", "anthropic", "translate")))
    # A Tamil story goes through English and back, so it costs twice its source length.
    # A budget below that finishes no story at all while still spending characters.
    tcfg = live.get("translate", {})
    source_chars = int(tcfg.get("max_source_chars", 700))
    run_budget = int(tcfg.get("max_chars_per_run", 0))
    check("a run can afford at least one whole story",
          run_budget >= source_chars * 2,
          "budget %d, a Tamil story costs about %d" % (run_budget, source_chars * 2))

    check("free providers pace their requests",
          all(float(live.get(n, {}).get("min_interval_seconds", 0)) > 0
              for n in ("gemini", "translate")),
          "gemini=%s translate=%s" % (live.get("gemini", {}).get("min_interval_seconds"),
                                      live.get("translate", {}).get("min_interval_seconds")))

    # --- the whole pipeline, on a throwaway copy of the repo --------------------
    work = Path(tempfile.mkdtemp(prefix="yarl-selftest-"))
    try:
        for rel in ("scripts", "config", "templates", "content", "site", "data"):
            if (ROOT / rel).exists():
                shutil.copytree(ROOT / rel, work / rel,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (work / "data").mkdir(exist_ok=True)

        ai_enrich.ROOT = build.ROOT = work
        ai_enrich.STORE_FILE = work / "data" / "fetched.json"
        ai_enrich.TEXTS_FILE = work / "data" / "texts.json"
        ai_enrich.CONFIG_FILE = work / "config" / "ai.json"
        build.SITE, build.TEMPLATES = work / "site", work / "templates"
        build.NEWS_DIR = work / "site" / "news"

        # Nothing here calls a real service, so drop the pacing the live config uses to
        # stay inside a free tier's per-minute limit — otherwise this waits out a real
        # four-second gap per story and adds two minutes to every CI run.
        ai_cfg = json.loads((work / "config" / "ai.json").read_text(encoding="utf-8"))
        for block in ai_cfg.values():
            if isinstance(block, dict):
                block["min_interval_seconds"] = 0
        (work / "config" / "ai.json").write_text(
            json.dumps(ai_cfg, ensure_ascii=False), encoding="utf-8")

        # data/texts.json is gitignored, so it is absent on a fresh checkout and present
        # with whatever a local run last left. Write our own so the run is the same
        # everywhere: enough article text for the first 30 stories, and none after.
        store = json.loads((work / "data" / "fetched.json").read_text(encoding="utf-8"))
        article = ("இது ஒரு சோதனைக்கான செய்தி உரை. " * 20).strip()
        (work / "data" / "texts.json").write_text(
            json.dumps({i["id"]: article for i in store["items"][:30]}, ensure_ascii=False),
            encoding="utf-8")

        calls = {"n": 0}

        def stub(client, cfg, item, text):
            calls["n"] += 1
            n = calls["n"]
            if n % 5 == 0:   # the model judged this one too thin to report
                return {"enough_material": False, "headline": "", "lede": "", "body": [],
                        "category": "srilanka"}, TOKENS
            if n % 7 == 0:   # and declined this one outright
                return None
            return {
                "enough_material": True,
                "headline": "%s மாவட்டத்தில் %s தொடர்பான அறிவிப்பு" % (
                    TOWNS[n % len(TOWNS)], SUBJECTS[n % len(SUBJECTS)]),
                "lede": "%s பகுதியில் புதிய திட்டம் அறிவிக்கப்பட்டுள்ளது." % TOWNS[n % len(TOWNS)],
                "body": ["%s மாவட்டத்தில் புதிய திட்டம் ஆரம்பிக்கப்பட்டுள்ளது." % TOWNS[n % len(TOWNS)],
                         "இதனால் பல குடும்பங்கள் நன்மையடையும் எனத் தெரிவிக்கப்பட்டது."],
                "category": "jaffna",
            }, TOKENS

        # Stand in for whichever provider config/ai.json names, so this runs with no key,
        # no network and no provider SDK installed.
        ai_enrich.rewrite = stub
        ai_enrich.PROVIDERS = {name: (lambda cfg: None, stub) for name in ai_enrich.PROVIDERS}

        written = ai_enrich.enrich(limit=30, quiet=True)
        check("the rewrite step writes stories", written > 0, "wrote %d" % written)

        store = json.loads((work / "data" / "fetched.json").read_text(encoding="utf-8"))
        check("a story with no article text is left alone",
              all(not i.get("ai_body") and not i.get("ai_thin") for i in store["items"][30:]))
        thin = [i for i in store["items"] if i.get("ai_thin")]
        check("a story judged too thin is marked, not published",
              bool(thin) and all(not i.get("ai_body") for i in thin))
        check("the rewrite decides the section",
              any(i.get("category") == "jaffna" for i in store["items"] if i.get("ai_body")))

        published = build.build(verbose=False)
        check("the build publishes the rewritten stories", published > 0, "published %d" % published)

        pages = sorted((work / "site" / "news").glob("*.html"))
        check("a page is written per published story", len(pages) == published,
              "%d pages, %d published" % (len(pages), published))

        html = "\n".join(p.read_text(encoding="utf-8") for p in pages)
        leaked = [name for name in PUBLISHERS if name in html]
        check("no publisher is named on any page", not leaked, ", ".join(leaked))
        check("no source box is rendered", "source-box" not in html)
        check("each story is labelled machine-assisted",
              all("ai-note" in p.read_text(encoding="utf-8") for p in pages))

        # news.js embeds config/ads.json too, and an image ad legitimately carries a
        # "link". Check the stories themselves, not the whole file.
        news_js = (work / "site" / "data" / "news.js").read_text(encoding="utf-8")
        payload = json.loads(news_js[news_js.index("{"):news_js.rstrip().rstrip(";").rindex("}") + 1])
        story_keys = set()
        for story in payload.get("items", []):
            story_keys.update(story)
        check("the browser payload carries no publisher", "source" not in story_keys)
        check("the browser payload carries no source link", "link" not in story_keys)
        check("the browser payload still carries the stories", len(payload.get("items", [])) > 0)

        rss = (work / "site" / "rss.xml")
        if rss.exists():
            body = rss.read_text(encoding="utf-8")
            check("the feed names no publisher", not [n for n in PUBLISHERS if n in body])

        # An unrewritten store must leave the existing site alone rather than empty it.
        for item in store["items"]:
            for key in ("ai_body", "ai_title", "ai_summary"):
                item.pop(key, None)
        (work / "data" / "fetched.json").write_text(
            json.dumps(store, ensure_ascii=False), encoding="utf-8")
        before = len(list((work / "site" / "news").glob("*.html")))
        refused = False
        try:
            build.build(verbose=False)
        except build.SiteNotReady:
            refused = True
        after = len(list((work / "site" / "news").glob("*.html")))
        check("an empty rewrite leaves the site untouched", before == after and before > 0)
        check("an empty rewrite is reported as a failure", refused)

        # A refused build must not stop fetch_news saving what it did write: stories
        # accumulate across runs, and discarding them would stall the site forever.
        source = (ROOT / "scripts" / "fetch_news.py").read_text(encoding="utf-8")
        guard = source.split("except build.SiteNotReady")[1][:400]
        check("a refused build still saves the run's work", "return 2" not in guard)

        # ...and the saving itself has to survive a remote that moved, or the work is
        # committed and then thrown away by a rejected push.
        workflow = (ROOT / ".github" / "workflows" / "update-news.yml").read_text(encoding="utf-8")
        check("the scheduled run saves through the retrying script",
              "scripts/save_news.sh" in workflow
              and (ROOT / "scripts" / "save_news.sh").exists())

        # These run on macOS here and on Linux in CI, where the shell utilities differ.
        # `mktemp -t name` is the one that bit: fine in BSD, rejected by GNU.
        import subprocess
        shell_scripts = sorted((ROOT / "scripts").glob("*.sh"))
        bad_syntax = [f.name for f in shell_scripts
                      if subprocess.run(["bash", "-n", str(f)], capture_output=True).returncode]
        check("the shell scripts parse", not bad_syntax, ", ".join(bad_syntax))
        bsd_only = [f.name for f in shell_scripts
                    if re.search(r"mktemp\s+-t\s+[^\s]*$", f.read_text(encoding="utf-8"),
                                 re.MULTILINE)]
        check("no BSD-only mktemp templates", not bsd_only, ", ".join(bsd_only))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    run()
    print()
    if failures:
        print("%d check(s) failed: %s" % (len(failures), ", ".join(failures)))
        sys.exit(1)
    print("All checks passed.")
    sys.exit(0)
