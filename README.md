# யாழ் முரசு — Jaffna Tamil News Website

A Tamil news site for Jaffna and the Northern Province. It fetches the latest news from
trusted publishers automatically, and you can add your own stories with photos and videos.

Uses only Python 3 (no packages to install). The website is plain HTML/CSS/JS, so it can be
hosted anywhere (GitHub Pages, Netlify, cPanel hosting…).

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
| `scripts/ai_enrich.py` | Tamil summaries + English→Tamil translation (needs an API key) |
| `scripts/make_card.py` | Daily share image for Instagram/Facebook |
| `config/ai.json` | AI settings (model, how many per run, on/off) |
| `scripts/publish.sh` | Send your posts/photos/ads to GitHub so they go live |
| `scripts/update.sh` | What the scheduler runs (fetch → build → optional `scripts/deploy.sh`) |
| `scripts/schedule_mac.sh` | Turn auto-updates on/off on this Mac |
| `site/` | **The finished website — upload this folder** |

## Where the news comes from

| Source | Language | What you get |
|---|---|---|
| அத தெரண தமிழ் (adaderanatamil.lk) | Tamil | headline, summary, link |
| அரச செய்திச் சேவை (tamil.news.lk) — official government news portal | Tamil | headline, summary, link |
| வட மாகாண சபை (np.gov.lk) — Northern Provincial Council | English → Tamil | headline, summary, link |
| வீரகேசரி (front page + article pages) | Tamil | headline, photo, opening lines, link |
| BBC News தமிழ் | Tamil | headline, summary, link |
| Tamil Guardian | English → Tamil | headline, summary, link |
| Google News (Jaffna & Northern districts) | Tamil | headline + link only |

Categories: யாழ்ப்பாணம் (includes Kilinochchi, Mullaitivu, Vavuniya, Mannar), இலங்கை, உலகம், விளையாட்டு.

**What is shown, and why.** Each story shows the publisher's own summary (the part they syndicate),
plus — when AI summaries are switched on — a short Tamil summary written in our own words, and a
button to the full article on the publisher's site. Full articles are never copied: the text belongs
to the publisher, and republishing it would be copyright infringement. Stories where we only have a
headline say so plainly.

## Tamil summaries and English→Tamil translation (optional, costs money)

`scripts/ai_enrich.py` asks Claude to write a 3-4 sentence Tamil summary from the publisher's excerpt,
and to translate English headlines (Northern Provincial Council, Tamil Guardian) into Tamil. Nothing is
invented: when there is too little text, the story keeps just its headline. Summaries are labelled on the
page as machine-assisted.

Set up:
1. Get an API key at console.anthropic.com.
2. On GitHub: repository → Settings → Secrets and variables → Actions → New repository secret,
   name `ANTHROPIC_API_KEY`. The workflow picks it up automatically.
3. On this Mac (optional): `export ANTHROPIC_API_KEY=sk-ant-...` before running, and the project
   venv (`.venv`) already has the SDK. The admin panel has a button for it.

Cost: roughly 40 stories per run. With the default `claude-opus-5` that is a few US dollars a month at
half-hourly updates; `claude-haiku-4-5` in `config/ai.json` is about five times cheaper with slightly
plainer Tamil. Set `"enabled": false` there to turn it off.

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
