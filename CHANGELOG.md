# Changelog

Notable changes to யாழ் முரசு. The `Auto-update news` commits the bot makes every few
hours are not listed — they are news, not changes to how the site works.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). There are no
version numbers: the site is continuously deployed, so entries are dated instead.

---

## 2026-09-26

The site stopped republishing publishers' text and started writing its own.

### Changed — every story is now our own Tamil writing

Previously a story was a publisher's headline and syndicated excerpt, shown with their
name and a link. A third of them were Google News stubs with no text at all, and English
stories were never translated, so they sat held back indefinitely.

Now each story is read in full from the publisher's own page and rewritten in Tamil —
fresh headline, lede, body and section. English sources are translated in the same pass.
No publisher's wording is reproduced and no publisher is named in anything a reader sees:
not on cards, story pages, the ticker, the share card, the RSS feed, or the JSON the
browser loads.

This is a policy change as much as a code change. The trust pages, the footer and the
README were rewritten to describe how stories are actually made, and `CLAUDE.md` records
the rule so it is not undone by accident.

**A key is required.** Nothing new publishes without one, because there is nothing to
publish until a story has been rewritten. See `README.md` → The Tamil rewrite.

### Added

- **Three rewrite providers**, chosen by `provider` in `config/ai.json`:
  - `auto` (default) — Gemini or Claude when their key is set, translation when neither
    is, so the site publishes with no key and upgrades itself when one appears.
  - `gemini` — Google's free tier. A key from aistudio.google.com, no card.
  - `anthropic` — Claude. The best Tamil, but every story costs money.
  - `translate` — no key and no language model: English is translated into Tamil, Tamil
    goes through English and back. Short briefs in plainer Tamil, bounded by MyMemory's
    daily character allowance.
- `scripts/selftest.py` — the project's only automated test. It stubs the provider and
  asserts, offline and for free, that a story publishes only once rewritten, that no
  publisher's name or link reaches a page, the feed or the browser payload, that every
  story stays labelled machine-assisted, and that an empty rewrite leaves the existing
  site alone. CI runs it on every push.
- `scripts/ai_enrich.py --check` — reports the provider, whether its key is set, and
  whether the model name is one that key can use. Model names move; this turns a
  confusing mid-run failure into a clear pre-flight one.
- `scripts/merge_store.py` and `scripts/save_news.sh` — fold two copies of the story
  store together, so work from the Mac and work from GitHub can both survive.
- Self-hosted Noto Tamil. The head template had dropped the Google Fonts link without
  replacing it, so Tamil had been falling back to whatever the device happened to have.
- Styles for the five trust pages, which had none and would have rendered unstyled.
- Newswire and The Island as sources. A GitHub runner cannot reach Ada Derana Tamil or
  Virakesari (HTTP 403), so English outlets it *can* reach now carry the site — which
  makes translation load-bearing rather than a nicety.

### Removed

- **Google News as a source.** Its RSS links are opaque redirects that resolve only
  through Google's own endpoint, so those stories could never be more than a bare
  headline. They were a third of the store.

### Fixed

- A refused build discarded the run's rewrites, so the story count could never grow and
  the site could never reach the threshold to publish. It is now a warning, and the work
  is saved.
- The per-run translation budget was smaller than one story costs, so runs spent
  characters, produced nothing, and reported success.
- A scheduled run pushed without pulling, so any competing push left its commit stranded
  and its stories lost.
- `mktemp -t name` works on macOS and is rejected by GNU mktemp on the Linux runner.
- A translation that came back in the source language was published as though it were
  Tamil.
- Near-duplicate headlines from different outlets collapsed into one — but the rule was
  loose enough to also merge two unrelated stories that named the same minister.
- Pages that yielded no article text, and stories whose rewrite kept failing, were
  retried on every run forever.
- `Content-Encoding: deflate` was decoded only in its raw form, so the commoner
  zlib-wrapped form produced garbage and the story was silently marked too thin.
- The share card and the browser payload still carried publisher names.
- The rewrite queue took stories newest-first, so a limited budget went to whatever
  happened to be newest — in practice BBC Tamil features rather than Northern Province
  news. It now works through Jaffna, then Sri Lanka, then sport and world.

### Notes for whoever runs this next

- **The cron lies.** `.github/workflows/update-news.yml` asks for every 30 minutes;
  GitHub throttles scheduled runs on shared runners and fires it about seven times a
  day. Check with `gh run list` and filter to `schedule` rows before sizing anything
  per-run. Getting this wrong is what caused the empty-run bug above.
- **On the `translate` provider, set `translate.email`.** MyMemory allows 5,000
  characters a day anonymously and 50,000 with an email — roughly 8 stories a day
  against 90.
- A fully offline rewrite was investigated and rejected: Argos Translate has no Tamil at
  all, and the Tamil models that exist (Opus-MT, IndicTrans2) need PyTorch and a couple
  of gigabytes, which a scheduled GitHub run cannot carry.

---

## Before 2026-09-26

Not recorded here. The site fetched headlines and excerpts from trusted publishers and
displayed them with attribution and a link to the original; see the git history.
