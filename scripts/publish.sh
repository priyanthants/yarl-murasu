#!/bin/bash
# Publish your own posts, uploaded photos and ad changes to GitHub.
# GitHub Actions then rebuilds the site and puts it live within about a minute.
#
# Only content/, config/ and site/uploads/ are committed. Generated files (site/, data/)
# are rebuilt by GitHub, so local copies are reset first to avoid clashing with the
# news bot's commits.
set -eu
cd "$(dirname "$0")/.."

git add content config site/uploads 2>/dev/null || git add content config
if git diff --cached --quiet; then
  echo "No new posts or ad changes to publish."
else
  git commit -q -m "Update posts and ads"
  echo "Saved your changes."
fi

# Drop locally generated files; GitHub regenerates them.
git checkout -- site data 2>/dev/null || true
git clean -fdq site/news site/data 2>/dev/null || true

git pull -q --rebase origin main
git push -q origin main
echo "Pushed to GitHub. The website updates in about a minute."

/usr/bin/env python3 scripts/build.py
