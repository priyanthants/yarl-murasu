#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Notify the private review app about a small batch of ready, unapproved stories."""
import datetime as dt
import json
import os
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORDER = {"jaffna": 0, "srilanka": 1, "sports": 2, "world": 3}


def candidates(store, reviews, now, limit=40):
    cutoff = now - dt.timedelta(hours=72)
    selected = []
    for item in store.get("items", []):
        if not item.get("ai_body") or not item.get("ai_title"):
            continue
        if reviews.get(item["id"], {}).get("state", "pending") != "pending":
            continue
        try:
            published = dt.datetime.fromisoformat(item["published"].replace("Z", "+00:00"))
        except (KeyError, ValueError, TypeError):
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=dt.timezone.utc)
        if published < cutoff:
            continue
        selected.append(item)
    # Send newest first, using the local-news priority only for equal timestamps.
    selected.sort(key=lambda i: ORDER.get(i.get("category"), 4))
    selected.sort(key=lambda i: i.get("published", ""), reverse=True)
    return [{"id": i["id"], "title": i["ai_title"]} for i in selected[:limit]]


def main():
    url = os.environ.get("REVIEW_API_URL", "").rstrip("/")
    key = os.environ.get("REVIEW_INGEST_KEY", "")
    if not url or not key:
        print("Review alerts are not connected yet; approved-only publishing remains active.")
        return 0
    store = json.loads((ROOT / "data" / "fetched.json").read_text(encoding="utf-8"))
    reviews = json.loads((ROOT / "data" / "reviews.json").read_text(encoding="utf-8")).get("items", {})
    batch = candidates(store, reviews, dt.datetime.now(dt.timezone.utc))
    if not batch:
        print("No fresh stories are waiting for a review alert.")
        return 0
    request = urllib.request.Request(
        url + "/internal/notify",
        data=json.dumps({"stories": batch}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Review-Ingest-Key": key},
        method="POST")
    with urllib.request.urlopen(request, timeout=25) as response:
        result = json.load(response)
    print("Review alerts: %d sent to %d device(s)." %
          (result.get("notified", 0), result.get("devices", 0)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
