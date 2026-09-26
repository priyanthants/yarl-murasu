#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge two copies of data/fetched.json into one.

Ada Derana Tamil and Virakesari refuse GitHub's servers, so the Jaffna reporting on
this site can only be collected from a home connection. That means two machines write
to the same store: the scheduled GitHub run, and whatever is fetched and rewritten
here. Rebasing that file just produces conflicts, so scripts/publish.sh merges the two
copies instead.

A story known to both sides is kept once, preferring the copy that already carries a
Tamil rewrite (and, between two rewrites, the newer one).

Usage:
    python3 scripts/merge_store.py MINE THEIRS OUT
"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {"items": []}


def better(a, b):
    """Of two copies of one story, the one worth keeping."""
    if bool(a.get("ai_body")) != bool(b.get("ai_body")):
        return a if a.get("ai_body") else b
    if a.get("ai_at") and b.get("ai_at"):
        return a if a["ai_at"] >= b["ai_at"] else b
    return a if len(json.dumps(a, ensure_ascii=False)) >= len(json.dumps(b, ensure_ascii=False)) else b


def limits():
    """The same age and size caps fetch_news.py applies, so a merge cannot grow the
    store past them — this file is rewritten on every run and its diff is pushed."""
    try:
        cfg = json.loads((ROOT / "config" / "sources.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        cfg = {}
    return cfg.get("max_age_days", 7), cfg.get("max_store_items", 400)


def merge(mine, theirs):
    by_id = {}
    for item in list(theirs.get("items", [])) + list(mine.get("items", [])):
        existing = by_id.get(item["id"])
        by_id[item["id"]] = better(item, existing) if existing else item

    max_age_days, max_items = limits()
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=max_age_days)
    fresh = []
    for item in by_id.values():
        try:
            when = dt.datetime.fromisoformat(str(item.get("published", "")).replace("Z", "+00:00"))
        except ValueError:
            fresh.append(item)          # undated: keep it, the build decides
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=dt.timezone.utc)
        if when >= cutoff:
            fresh.append(item)

    fresh.sort(key=lambda i: i.get("published", ""), reverse=True)
    return {"updated": dt.datetime.now(dt.timezone.utc).isoformat(),
            "items": fresh[:max_items]}


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    mine, theirs, out = (Path(p) for p in sys.argv[1:4])
    merged = merge(load(mine), load(theirs))
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(out)
    written = sum(1 for i in merged["items"] if i.get("ai_body"))
    print("Merged store: %d stories, %d already written in Tamil." % (len(merged["items"]), written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
