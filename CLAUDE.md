# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Tamil news website for Jaffna, Sri Lanka ("யாழ் முரசு"). A Python pipeline fetches news from trusted
publishers and generates a static site, deployed to GitHub Pages at
https://priyanthants.github.io/yarl-murasu/ (repo `priyanthants/yarl-murasu`).

## Commands

```bash
python3 scripts/admin.py            # admin panel + preview on http://localhost:8000 (also /admin)
python3 scripts/fetch_news.py       # fetch sources → AI step → build   (--no-ai, --no-build, -v)
python3 scripts/build.py            # regenerate site/ from config + content + data
scripts/publish.sh                  # push own posts/ads to GitHub so they go live
python3 scripts/make_card.py        # daily Instagram image (--size square|portrait|story, --skip-existing)
.venv/bin/python scripts/ai_enrich.py   # Tamil summaries + English→Tamil translation
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
  `site/assets/**` (css/js/img), `site/uploads/**`, `scripts/*`
- **Generated (never hand-edit):** `site/index.html`, `site/news/*.html`, `site/data/news.js`,
  `site/rss.xml`, `site/sitemap.xml`, `data/fetched.json`, `site/cards/*.png`

`build.py` renders templates (`{{placeholder}}` substitution, partials `_head/_header/_footer`) and
writes `site/data/news.js` as `window.NEWS_DATA`, which `site/assets/js/app.js` renders in the browser.
Story pages are pre-generated so Facebook/X link previews work without JavaScript.

`build.display(item)` decides what the reader sees (Tamil title from `title_ta`, Tamil summary from
`ai_summary`). Call it before rendering anything reader-facing — `make_card.py` does too.

## Content policy (do not break)

- Never republish full articles. Store at most `excerpt_chars` (300) of a publisher's text, always with
  the publisher's name and a link to the original.
- `data/texts.json` caches article text purely as AI input. It is gitignored and must never be committed.
- AI-written summaries must stay labelled on the page as machine-assisted (`.ai-note`).
- Only publishers listed in `config/sources.json` → `trusted_domains` are published.
- Ada Derana Tamil and Virakesari return HTTP 403 to data-centre IPs, so GitHub runs skip them. This is
  the publishers' choice — do not attempt to bypass it (proxies, IP rotation, spoofing).
- `scripts/fetch_news.py` respects `delay_seconds` between article fetches (Virakesari's robots.txt asks
  for a 20s crawl delay). Keep it.

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

- `ANTHROPIC_API_KEY` enables the AI step (GitHub repository secret; exported locally). Without it the
  step is skipped silently and the site still builds.
- `config/ai.json` sets the model (`claude-opus-5`) and per-run limits; `config/site.json` holds
  `site_url`, social links and categories; `config/ads.json` holds ad slots.
- Never commit API keys, and do not put the owner's email address into site output.
