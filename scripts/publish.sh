#!/bin/bash
# Publish your own posts, uploaded photos, ad changes — and any stories this Mac has
# already written in Tamil — to GitHub. GitHub Actions rebuilds the site and puts it
# live within about a minute.
#
# Ada Derana Tamil and Virakesari refuse GitHub's servers, so the Jaffna reporting they
# carry can only be collected here. data/fetched.json therefore holds real work, and is
# merged with GitHub's copy rather than thrown away. Only the generated pages under
# site/news and site/data are discarded, because GitHub rebuilds those; everything else
# under site/ (the stylesheet, the script, the fonts, your uploads) is yours to edit.
set -eu
cd "$(dirname "$0")/.."

# Keep this Mac's stories in a real file, not a temp one: if anything below fails, the
# rewrites it holds are hours of work, and the next run must not lose them. A backup
# left by an earlier failed run is folded in rather than overwritten or trusted alone.
MINE="data/fetched.local.json"
if [ -f "$MINE" ]; then
  python3 scripts/merge_store.py "$MINE" data/fetched.json "$MINE"
else
  cp data/fetched.json "$MINE" 2>/dev/null || echo '{"items":[]}' > "$MINE"
fi
trap 'echo "Stopped early. Your stories are safe in $MINE; run this script again."' ERR

# A rebase needs a clean tree. Drop only what GitHub regenerates.
git checkout -- data 2>/dev/null || true
git checkout -- site/news site/data site/index.html site/rss.xml site/sitemap.xml 2>/dev/null || true
git clean -fdq site/news site/data 2>/dev/null || true

git add content config site/uploads site/assets 2>/dev/null || git add content config
if git diff --cached --quiet; then
  echo "No new posts, photos, ads or design changes to publish."
else
  git commit -q -m "Update posts, ads and site files"
  echo "Saved your changes."
fi

git pull -q --rebase origin main

# Now fold this Mac's stories into GitHub's copy, keeping whichever side has the rewrite.
python3 scripts/merge_store.py "$MINE" data/fetched.json data/fetched.json
git add data/fetched.json
if git diff --cached --quiet; then
  echo "No new stories from this Mac."
else
  git commit -q -m "Add stories fetched and written on this Mac"
fi

git push -q origin main
rm -f "$MINE"
echo "Pushed to GitHub. The website updates in about a minute."

/usr/bin/env python3 scripts/build.py || true
