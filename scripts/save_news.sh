#!/bin/bash
# Commit and push what a scheduled run produced, even if the remote moved underneath it.
#
# The bot is usually the only writer, but not always: a publish.sh from the Mac, or any
# edit pushed while a run is in flight, leaves the push rejected. The run's rewrites are
# real work — on the translation provider a run may produce a single story — so losing
# them means the site never accumulates enough to publish.
#
# On a rejected push, this keeps this run's stories, takes the remote's commit, folds the
# two stores together and rebuilds, rather than resolving a conflict in generated files.
set -eu
cd "$(dirname "$0")/.."

git config user.name "news-bot"
git config user.email "news-bot@users.noreply.github.com"

git add data site
if git diff --cached --quiet; then
  echo "Nothing new to save."
  exit 0
fi
git commit -q -m "Auto-update news"

MINE="$(mktemp -t fetched)"
trap 'rm -f "$MINE"' EXIT

for attempt in 1 2 3; do
  if git push -q origin HEAD:main 2>/dev/null; then
    echo "Saved (attempt $attempt)."
    exit 0
  fi
  echo "Remote moved; merging this run's stories into it (attempt $attempt)."
  cp data/fetched.json "$MINE"
  git fetch -q origin main
  git reset --hard -q origin/main
  python3 scripts/merge_store.py "$MINE" data/fetched.json data/fetched.json
  # The build may refuse when too few stories are ready yet; that is not an error here.
  python3 scripts/build.py || true
  git add data site
  if git diff --cached --quiet; then
    echo "Remote already has everything from this run."
    exit 0
  fi
  git commit -q -m "Auto-update news"
done

echo "Could not save this run's work after 3 attempts." >&2
exit 1
