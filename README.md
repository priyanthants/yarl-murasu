# யாழ் முரசு — Jaffna Tamil News Website

A Tamil news site for Jaffna and the Northern Province. It reads the latest reports from
trusted publishers, writes each one afresh in its own Tamil, and publishes that — so every
story on the site is our own writing, in Tamil, whatever language it started in. You can
add your own stories with photos and videos too.

The website is plain HTML/CSS/JS, so it can be hosted anywhere (GitHub Pages, Netlify,
cPanel hosting…).

> **One thing must be set up before anything publishes.** The Tamil rewrite runs on the
> Claude API, so the repository needs an `ANTHROPIC_API_KEY` secret. Without it no story
> can be rewritten, nothing new goes live, and the site keeps serving the pages it already
> has. See [The Tamil rewrite](#the-tamil-rewrite--required--costs-money) below.

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
| `scripts/ai_enrich.py` | Rewrites every story in our own Tamil, translating English (needs an API key) |
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

Categories: யாழ்ப்பாணம் (includes Kilinochchi, Mullaitivu, Vavuniya, Mannar), இலங்கை, உலகம், விளையாட்டு.
The rewrite step picks the section after reading the whole story, so a report lands where it belongs
rather than wherever its headline keywords pointed.

**What is shown, and why.** Every story on the site is written here, in Tamil, from the facts in a
report published by a trusted news organisation. No publisher's text is reproduced and no publisher
is named on the page — what you read is our own writing, and it is labelled as machine-assisted.
Stories are held back, not published half-finished, when there was too little to write from.

## The Tamil rewrite (required — costs money)

`scripts/ai_enrich.py` gives Claude the full article a publisher put out and asks for a fresh Tamil
report written from the facts in it: a new headline, a one-line lede and a few paragraphs of body,
plus which section the story belongs in. English sources are translated in the same pass.

Nothing is invented — the rewrite may only use what the source states — and when there is too little
to write from, the story is held back instead of published as a bare headline.

**This step is not optional any more.** Since every story on the site is our own writing, a run
without `ANTHROPIC_API_KEY` publishes nothing new: the GitHub workflow stops with a named error and
`build.py` leaves the site exactly as it was rather than emptying it.

Set up:
1. Get an API key at console.anthropic.com.
2. On GitHub: repository → Settings → Secrets and variables → Actions → New repository secret,
   name `ANTHROPIC_API_KEY`. The workflow picks it up automatically.
3. On this Mac (optional): `export ANTHROPIC_API_KEY=sk-ant-...` before running, and the project
   venv (`.venv`) already has the SDK. The admin panel has a button for it.

Check what is waiting without spending anything:

```bash
.venv/bin/python scripts/ai_enrich.py --dry-run --no-build
```

**Cost — read this before switching it on.** A rewrite is much bigger than the old one-paragraph
summary: it reads a whole article and writes a whole story. On the default `claude-opus-5` expect
very roughly 5-8 US cents per story. Clearing the ~200 stories already waiting costs somewhere near
10-15 dollars, and after that the day-to-day rate depends on how many new stories the sources carry.

`config/ai.json` holds every knob:

| Setting | What it does |
|---|---|
| `model` | `claude-haiku-4-5` is roughly five times cheaper, with plainer Tamil; `claude-sonnet-5` sits in between |
| `effort` | `low` / `medium` / `high` — how much thinking each story gets |
| `max_items_per_run` | Ceiling per run (40), so one run can never surprise you |
| `concurrency` | How many stories are written at once |
| `enabled` | `false` stops the rewrite entirely |

Watch the first day at console.anthropic.com and turn `model` or `effort` down if it costs more than
you want it to.

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
