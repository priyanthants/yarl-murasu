#!/bin/bash
# Fetch the latest news and rebuild the site. Used by the scheduler (launchd / cron).
# If scripts/deploy.sh exists and is executable, it runs afterwards to publish the site
# (for example: rsync to your web host, or git push to GitHub Pages).
set -u
cd "$(dirname "$0")/.." || exit 1
mkdir -p logs
{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') ==="
  /usr/bin/env python3 scripts/fetch_news.py
  status=$?
  if [ $status -eq 0 ] && [ -x scripts/deploy.sh ]; then
    scripts/deploy.sh
  fi
} >> logs/update.log 2>&1
