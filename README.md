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
| `scripts/update.sh` | What the scheduler runs (fetch → build → optional `scripts/deploy.sh`) |
| `scripts/schedule_mac.sh` | Turn auto-updates on/off on this Mac |
| `site/` | **The finished website — upload this folder** |

## How news fetching works

1. Searches Google News (Tamil, Sri Lanka) for யாழ்ப்பாணம், the Northern districts and இலங்கை,
   and reads BBC தமிழ், Ada Derana and Tamil Guardian feeds directly.
2. **Keeps only publishers listed in `trusted_domains`** (Virakesari, BBC, Ada Derana, Newsfirst,
   Tamil Mirror, Thinakaran, ITN, Hiru, government sites, Hindu Tamil, Dinamani…). Forums,
   blogs and unknown sites are skipped. To add or remove a publisher, edit that list.
3. Sorts each story into a category (யாழ்ப்பாணம், வடமாகாணம், இலங்கை …) using keywords.
4. Stores **only the headline, a short summary and the link**. Each story page has a
   "முழுச் செய்தியை வாசிக்க" button to the original publisher. Full articles are never copied,
   which keeps you clear of copyright problems.
5. Removes stories older than 10 days (`max_age_days`).

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
