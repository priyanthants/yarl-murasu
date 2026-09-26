# யாழ் முரசு — Jaffna Tamil News Website

A Tamil news site for Jaffna and the Northern Province. It reads the latest reports from
trusted publishers, writes each one afresh in its own Tamil, and publishes that — so every
story on the site is our own writing, in Tamil, whatever language it started in. You can
add your own stories with photos and videos too.

The website is plain HTML/CSS/JS, so it can be hosted anywhere (GitHub Pages, Netlify,
cPanel hosting…).

> **It runs with no API key**, rewriting by machine translation alone — short briefs in plain
> Tamil. Adding a **free** Gemini key from
> [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (no card) as the repository
> secret `GEMINI_API_KEY` upgrades it to a proper rewrite automatically, with nothing else to
> change. See [The Tamil rewrite](#the-tamil-rewrite) below.

## Quick start

```bash
python3 scripts/admin.py
```
Then open:
- **http://localhost:8000/** — the website
- **http://localhost:8000/admin** — admin panel (add news, photos, videos, ads; fetch news)

## Live website

**https://priyanthants.github.io/yarl-murasu/** (repository: github.com/priyanthants/yarl-murasu)

GitHub fetches the news every 30 minutes and republishes the site on its own; your Mac can be off.

**Adding your own news:** run `python3 scripts/admin.py`, add the story/photos/videos/ads, check the
preview, then press **நேரலையில் வெளியிடு (Publish)** in the admin panel (or run `scripts/publish.sh`).
It goes live in about a minute.

## What's where

| Path | Purpose |
|---|---|
| `config/site.json` | Site name, tagline, **site_url** (set this once you have a domain), social media links, categories |
| `config/sources.json` | News sources, **trusted publisher list**, category keywords |
| `config/ads.json` | Ad slots (also editable from the admin panel) |
| `content/posts.json` | Your own stories (written by the admin panel) |
| `data/fetched.json` | Fetched news (auto) |
| `scripts/fetch_news.py` | Fetch latest news + rebuild the site |
| `scripts/build.py` | Rebuild the site only |
| `scripts/admin.py` | Local admin panel + preview server |
| `scripts/ai_enrich.py` | Rewrites every story in our own Tamil, translating English (Gemini free tier or Claude) |
| `scripts/make_card.py` | Daily share image for Instagram/Facebook |
| `config/ai.json` | AI settings (model, how many per run, on/off) |
| `scripts/publish.sh` | Send your posts/photos/ads to GitHub so they go live |
| `scripts/update.sh` | What the scheduler runs (fetch → build → optional `scripts/deploy.sh`) |
| `scripts/schedule_mac.sh` | Turn auto-updates on/off on this Mac |
| `site/` | **The finished website — upload this folder** |

The generated site also includes `about.html`, `editorial-policy.html`, `corrections.html`,
`privacy.html` and `contact.html`. The footer links to these trust and reader-information pages.

## Where the news comes from

| Source | Language | Reachable from GitHub |
|---|---|---|
| அத தெரண தமிழ் (adaderanatamil.lk) | Tamil | no — 403 |
| வீரகேசரி (front page + local desk) | Tamil | no — 403 |
| BBC News தமிழ் | Tamil | yes |
| அரச செய்திச் சேவை (tamil.news.lk) — official government news portal | Tamil | yes |
| வட மாகாண சபை (np.gov.lk) — Northern Provincial Council | English → Tamil | yes |
| Tamil Guardian | English → Tamil | yes |
| Ada Derana (adaderana.lk) | English → Tamil | yes |
| Newswire (newswire.lk) | English → Tamil | yes |
| The Island (island.lk) | English → Tamil | yes |

**Two Tamil sources only work from a home internet connection.** Ada Derana Tamil and Virakesari
block requests from data-centre servers (HTTP 403), so the half-hourly GitHub run cannot use them —
which is why several English Sri Lankan outlets are in the list: they answer from anywhere and are
translated into Tamil like everything else. To pull the two blocked sources in, run
`python3 scripts/fetch_news.py` on your Mac (or switch on `scripts/schedule_mac.sh`) and press
Publish. Do not try to work around the block — it is their decision to make.

Stories written on your Mac are not lost when GitHub publishes its own: `scripts/publish.sh` merges
the two sets, keeping whichever copy already has the Tamil rewrite. So the practical setup for strong
Jaffna coverage is both at once — GitHub every 30 minutes for what it can reach, and
`scripts/schedule_mac.sh on` for the two Tamil papers only your home connection can.

Categories: யாழ்ப்பாணம் (includes Kilinochchi, Mullaitivu, Vavuniya, Mannar), இலங்கை, உலகம், விளையாட்டு.
The rewrite step picks the section after reading the whole story, so a report lands where it belongs
rather than wherever its headline keywords pointed.

**What is shown, and why.** Every story on the site is written here, in Tamil, from the facts in a
report published by a trusted news organisation. No publisher's text is reproduced and no publisher
is named on the page — what you read is our own writing, and it is labelled as machine-assisted.
Stories are held back, not published half-finished, when there was too little to write from.

## The Tamil rewrite

`scripts/ai_enrich.py` gives the model the full article a publisher put out and asks for a fresh
Tamil report written from the facts in it: a new headline, a one-line lede and a few paragraphs of
body, plus which section the story belongs in. English sources are translated in the same pass.

Nothing is invented — the rewrite may only use what the source states — and when there is too little
to write from, the story is held back instead of published as a bare headline.

**This step is not optional.** Since every story on the site is our own writing, a run with no key
publishes nothing new: the GitHub workflow stops with a named error and `build.py` leaves the site
exactly as it was rather than emptying it.

### Who writes it

`provider` in `config/ai.json` picks one. Switching is a one-word edit; the workflow installs both.

`auto` is the default and is what you want: it uses Gemini or Claude when their key is set, and
falls back to translation when neither is. So the site publishes with no key at all, and upgrades
itself to a proper rewrite the moment you add one — nothing else to change.

| Provider | Needs a key | Quality | Notes |
|---|---|---|---|
| `gemini` | Free key | Good | Key from [aistudio.google.com/apikey](https://aistudio.google.com/apikey), no card. Rate limited per minute and per day, so a run writes what it can and the next one continues. Google may use free-tier content to improve their products. |
| `anthropic` | Paid key | Best | Noticeably better Tamil. Roughly 5–8 US cents per story. |
| `translate` | **No key at all** | Plainest | No language model. See below. |

### The `translate` provider — no key, no AI model

It uses machine translation only:

- An **English** story is translated into Tamil. The Tamil is new text by construction — the
  publisher wrote in English.
- A **Tamil** story is sent through English and back. The same facts return in different Tamil
  wording, which is a real re-wording rather than a copy.

Be clear about what you get. It writes a **short brief**, not a full article: about 900 characters
of the source, turned into a headline, a lede and two or three short paragraphs. It reads plainer
than a model-written story, and it follows the original's sentence order much more closely — it is
re-wording, not re-reporting. Section headings come from keyword matching rather than from reading
the story, and it cannot judge whether a page holds a real story, so weak sources get through more
often.

It uses [MyMemory](https://mymemory.translated.net), which allows **5,000 characters a day
anonymously and 50,000 with an email address**. **Put your email in `translate.email` in
`config/ai.json`** — it is the difference between a usable site and a stalled one:

| | Per day |
|---|---|
| No email | 2–5 stories |
| With an email | ~55 English stories, or ~27 Tamil ones (they cost double, going through English and back) |

`max_chars_per_run` (1,000) divides that allowance across the half-hourly runs, so the site gains a
story or so every half hour rather than spending the day's quota in one go. Raise it if you run the
fetch by hand instead of on a schedule.

A fully offline option is not practical here: Argos Translate, the usual local translation library,
has no Tamil at all, and the Tamil models that do exist (Opus-MT, IndicTrans2) need PyTorch and a
couple of gigabytes, which a half-hourly GitHub run cannot carry.

Set up (skip entirely if you use `translate`, which needs nothing):
1. Get a key — free at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) for Gemini,
   or console.anthropic.com for Claude.
2. On GitHub: repository → Settings → Secrets and variables → Actions → New repository secret,
   named `GEMINI_API_KEY` (or `ANTHROPIC_API_KEY`). The workflow picks it up automatically.
3. On this Mac (optional): `export GEMINI_API_KEY=...` before running. The admin panel has a button.

Check it is wired up correctly before a run — this reports the provider, whether its key is set,
and whether the model name is one your key can actually use:

```bash
python3 scripts/ai_enrich.py --check --no-build
```

Before spending anything, see what is queued — this calls nothing:

```bash
.venv/bin/python scripts/ai_enrich.py --dry-run --no-build
```

Then try three stories on your Mac and read what comes back, before letting it loose on the
backlog:

```bash
export GEMINI_API_KEY=...
.venv/bin/python scripts/ai_enrich.py --limit 3
python3 scripts/admin.py          # then read them at http://localhost:8000/
```

If the Tamil is not what you want, change the model in `config/ai.json`, switch `provider` to
`anthropic`, or edit the instructions at the top of `scripts/ai_enrich.py` (they are in Tamil), and
run the same command again with `--redo`.

`config/ai.json` holds every knob. The shared ones sit at the top level, and each provider has its
own block:

| Setting | What it does |
|---|---|
| `provider` | `gemini` (free) or `anthropic` (paid) |
| `max_items_per_run` | Ceiling per run (40), so one run can never surprise you |
| `min_text_chars` | Below this much article text, a story is not sent at all |
| `max_attempts` | How many times a story that keeps failing is retried before it is left alone |
| `enabled` | `false` stops the rewrite entirely |
| `gemini.model` | `gemini-3.5-flash-lite` and `gemini-3.1-flash-lite` are lighter on the free quota; `gemini-3.8-flash` is the strongest |
| `gemini.concurrency` / `min_interval_seconds` | Lower the first and raise the second if you see rate-limit messages |
| `gemini.thinking_level` | `minimal` / `low` / `medium` / `high` — raise it if the Tamil reads poorly, lower it to stretch the free quota |
| `anthropic.model` / `effort` | `claude-haiku-4-5` is much cheaper with plainer Tamil; effort is `low`/`medium`/`high` |
| `translate.email` | Raises the daily allowance from 5,000 to 50,000 characters |
| `translate.max_source_chars` | How much of each article is used (900). Lower it to cover more stories a day |
| `translate.max_chars_per_run` | Stops one run spending the whole day's allowance |

**If you use the paid provider**, a rewrite reads a whole article and writes a whole story, so
expect very roughly 5–8 US cents each on `claude-opus-5` — somewhere near 10–15 dollars to clear the
backlog that is already waiting. Watch the first day at console.anthropic.com.

## Daily share image (Instagram / Facebook / WhatsApp)

```bash
python3 scripts/make_card.py                 # 1080x1080 square, today's top 4
python3 scripts/make_card.py --size portrait # 1080x1350
python3 scripts/make_card.py --size story    # 1080x1920
python3 scripts/make_card.py --id <story id> # one story
```
Images are written to `site/cards/` and can be downloaded from the admin panel, which also has a
button to make them. GitHub makes one automatically each day. Cards older than 14 days are deleted.
Instagram does not allow posting from a website, so download the image and post it from your phone.

## Automatic updates (while you are away)

**Option A: GitHub (recommended, runs in the cloud, free)**
1. Create a GitHub repository and push this folder to its `main` branch.
2. Repository → Settings → Pages → Source: **GitHub Actions**.
3. The workflow `.github/workflows/update-news.yml` then fetches news every 30 minutes and
   publishes the site at `https://<user>.github.io/<repo>/`. Set that address as `site_url`.

**Option B: This Mac**
```bash
scripts/schedule_mac.sh on        # every 30 min
scripts/schedule_mac.sh status
scripts/schedule_mac.sh off
```
The Mac must be on and awake. macOS may block background jobs from reading the
`Documents` folder. If `logs/launchd.log` shows "Operation not permitted", either move the project
out of Documents (e.g. `~/NEWSPAGE`) or give `/bin/bash` Full Disk Access
(System Settings → Privacy & Security). To publish to a web host after each update, create
`scripts/deploy.sh` (e.g. an `rsync` or `git push` command) and make it executable.

## Ads

In the admin panel, pick a slot (header 728×90, sidebar 300×250, between news, inside stories,
footer). Then upload a banner image plus a link, **or** paste ad-network code (Google AdSense).
Ads can have start/end dates, and several ads in one slot rotate. Empty slots show
"உங்கள் விளம்பரம் இங்கே". Turn that off with `placeholder_when_empty: false` in `config/ads.json`.

## Sharing

Every story has Facebook, X, WhatsApp, Instagram and copy-link buttons. Instagram has no web
share link: on phones the button opens the phone's share menu (which includes Instagram), and on
computers it copies the link to paste. Link previews on Facebook/X show the right title and photo
once `site_url` is set and the site is online.

## Before going live
- Set `site_url`, `contact_email` and your `social` links in `config/site.json`.
- Change the name/tagline if you like (`name`, `tagline`), then run `python3 scripts/build.py`.
- Check that the name "யாழ் முரசு" isn't already used by another publication.
