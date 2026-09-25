# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Tamil news website for Jaffna, Sri Lanka ("யாழ் முரசு"). A Python pipeline fetches news from trusted
publishers and generates a static site, deployed to GitHub Pages at
https://priyanthants.github.io/yarl-murasu/ (repo `priyanthants/yarl-murasu`).

## Commands

```bash
python3 scripts/admin.py            # admin panel + preview on http://localhost:8000 (also /admin)
python3 scripts/fetch_news.py       # fetch → read article pages → rewrite → build   (--no-ai, --no-text, --no-build, -v)
python3 scripts/build.py            # regenerate site/ from config + content + data
scripts/publish.sh                  # push own posts/ads to GitHub so they go live
python3 scripts/make_card.py        # daily Instagram image (--size square|portrait|story, --skip-existing)
.venv/bin/python scripts/ai_enrich.py   # rewrite every story in our own Tamil (--dry-run, --redo)
scripts/schedule_mac.sh on|off|status   # local launchd timer (optional; GitHub Actions is primary)
```

There is no test framework. Verify changes by running `python3 scripts/build.py`, then screenshot the
local preview with headless Chrome (see "Headless Chrome" below).

## Python environments

- Core scripts (`fetch_news`, `build`, `admin`, `make_card`) use **stdlib only** and must stay
  compatible with the system Python 3.9. Do not add third-party imports to them.
- `ai_enrich.py` needs the `anthropic` SDK (Python 3.10+), so it runs under `.venv` (Homebrew
  python3.12). `fetch_news.py` invokes it as a subprocess with `.venv/bin/python` when present.
  In CI, `pip install anthropic` on Python 3.12 covers it.

## Architecture

Source of truth → generated output:

- **Source (edit these):** `config/*.json`, `content/posts.json`, `templates/*.html`,
  `site/assets/**` (css/js/img/fonts), `site/uploads/**`, `scripts/*`
- **Generated (never hand-edit):** `site/index.html`, `site/news/*.html`, `site/data/news.js`, `site/data/chrome.js`,
  `site/rss.xml`, `site/sitemap.xml`, `data/fetched.json`, `site/cards/*.png`

`build.py` renders templates (`{{placeholder}}` substitution, partials `_head/_header/_footer`) and
writes `site/data/news.js` for the homepage plus the smaller `site/data/chrome.js` for story-page
navigation, ads and latest-news widgets. Both expose `window.NEWS_DATA` to `site/assets/js/app.js`.
Story pages are pre-generated so Facebook/X link previews work without JavaScript.

The build also generates five trust pages from `static_pages()` in `build.py`.

`build.hold_reason(item)` is the publication gate: a fetched story goes live only once
`ai_enrich.py` has written `ai_body` for it. That one rule also keeps out headline-only stubs and
untranslated English, because a story without a rewrite is exactly one of those. Held stories stay
in `data/fetched.json` and are retried on later runs.

`build.display(item)` decides what the reader sees (`ai_title`, `ai_summary`, `ai_body`). Call it
before rendering anything reader-facing — `make_card.py` does too.

`build.drop_repeats()` keeps one story per event. Several outlets cover the same announcement and
each is rewritten separately, so identical-headline matching never fires; it compares the words of
the Tamil headlines instead and keeps the earliest.

`build.build()` refuses to write anything when fewer than `min_publishable` (config/site.json)
stories are ready and others are being held. Without that, one broken AI run would replace a full
site with an empty one; instead the pages already in `site/` stay exactly as they are.

## Content policy (do not break)

- **Everything the reader sees is our own Tamil writing.** `ai_enrich.py` reads a publisher's report and
  writes a fresh one from the facts in it; no publisher's sentences, headline or wording is ever
  published, and no publisher is named anywhere in reader-facing output.
- The rewrite may only use what the source report states. Never let it add a fact, name, number or
  date that is not there, and never let it publish a story it judged too thin (`enough_material`).
- Stories are still only taken from publishers listed in `config/sources.json` → `trusted_domains`.
- AI-written stories must stay labelled on the page as machine-assisted (`.ai-note`), and the trust
  pages (`static_pages()`) must keep describing how stories are actually made. If you change the
  pipeline, change those pages in the same commit.
- `data/texts.json` caches publishers' article text purely as rewrite input. It is gitignored and must
  never be committed or served.
- Ada Derana Tamil and Virakesari return HTTP 403 to data-centre IPs, so GitHub runs skip them. This is
  the publishers' choice — do not attempt to bypass it (proxies, IP rotation, spoofing). The English
  sources (Ada Derana, Newswire, The Island, Tamil Guardian) are what a CI run actually gets, which is
  why English→Tamil translation carries the site.
- Google News is not a source: its RSS links are opaque redirects that resolve only through Google's
  own endpoint, so those stories can never be more than a bare headline. `fetch_news.fetchable()`
  drops them.
- `fetch_news.py` respects `article_delay_seconds` per domain (Virakesari's robots.txt asks for a 20s
  crawl delay) and `max_article_fetches` per run. Keep both.

## Git workflow

A `news-bot` GitHub Action commits regenerated news every 30 minutes, so the remote moves constantly.

- Always `git pull --rebase origin main` before pushing.
- Rebasing generated files causes mass conflicts. When that happens, do not resolve them by hand:
  reset to `origin/main`, restore source files from your commit (`git checkout <sha> -- scripts config
  templates content README.md .github`), then re-run `python3 scripts/build.py` and commit.
- For content-only changes (own posts, ads, uploads) use `scripts/publish.sh`, which does this safely.

## Conventions

- All reader-facing text is Sri Lankan Tamil; the admin panel is Tamil with short English glosses.
- Times are Asia/Colombo (`build.SL_TZ`). Use `build.tamil_date()` server-side and `timeAgo()` in
  `app.js` — do not print raw ISO timestamps to readers.
- `app.js` is plain ES5-style browser JS (no build step, no framework). CSS uses the custom properties
  defined at the top of `site/assets/css/style.css`; dark mode is handled there, so use the tokens.
- Category ids are `jaffna` (covers the whole Northern Province), `srilanka`, `world`, `sports`,
  defined in `config/site.json` and keyed by `category_keywords` in `config/sources.json`.

## Headless Chrome

`make_card.py` and screenshot checks use Chrome headless, which often writes the PNG but does not exit.
Wait for the output file and then terminate the process (see `make_card.render`); do not block on exit.
Headless Chrome also enforces a ~500px minimum window width, so narrower screenshots are cropped, not
a responsive bug.

## Secrets and config

- `ANTHROPIC_API_KEY` is **required**, not optional: every fetched story is rewritten in Tamil before
  it can be published, so without the key nothing new goes live. It is a GitHub repository secret
  (Settings → Secrets and variables → Actions) and an exported variable locally. The workflow fails
  with a named error when it is missing, and `build.py` leaves the existing site untouched.
- `config/ai.json` sets the model (`claude-opus-5`) and per-run limits; `config/site.json` holds
  `site_url`, social links and categories; `config/ads.json` holds ad slots.
- Never commit API keys, and do not put the owner's email address into site output.
