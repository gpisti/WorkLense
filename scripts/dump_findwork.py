#!/usr/bin/env python3
"""Fetch FindWork API results and dump to JSON for inspection.

Usage:  python scripts/dump_findwork.py [--keywords N] [--pages N]
        --keywords N   how many keywords to try (default: 5)
        --pages N      max pages per keyword (default: 2)
"""
import argparse
import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config.settings import settings

API_URL = "https://findwork.dev/api/jobs/"
REQUEST_INTERVAL = 1.1

SAMPLE_KEYWORDS = [
    "software", "backend", "data engineer", "devops", "python",
    "machine learning", "frontend", "cloud", "security", "mobile",
]


def fetch(keyword: str, max_pages: int, api_key: str) -> list[dict]:
    import requests

    results = []
    url = API_URL
    page = 0
    last_req = 0.0

    while url and page < max_pages:
        elapsed = time.time() - last_req
        if elapsed < REQUEST_INTERVAL:
            time.sleep(REQUEST_INTERVAL - elapsed)
        last_req = time.time()

        params = {"search": keyword} if url == API_URL else None
        r = requests.get(
            url,
            headers={"Authorization": f"Token {api_key}"},
            params=params,
            timeout=30,
        )

        if r.status_code == 429:
            print(f"  Rate limited on '{keyword}', waiting 60s...")
            time.sleep(60)
            continue

        r.raise_for_status()
        data = r.json()
        jobs = data.get("results", [])
        if not jobs:
            break

        results.extend(jobs)
        print(f"  '{keyword}' page {page + 1}: {len(jobs)} jobs (total so far: {len(results)})")
        url = data.get("next")
        page += 1

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keywords", type=int, default=5)
    parser.add_argument("--pages", type=int, default=2)
    args = parser.parse_args()

    api_key = settings.FINDWORK_API_KEY
    if not api_key:
        print("FINDWORK_API_KEY not set in .env")
        sys.exit(1)

    keywords = SAMPLE_KEYWORDS[: args.keywords]
    all_jobs: list[dict] = []
    seen_ids: set[str] = set()

    for kw in keywords:
        print(f"Fetching: {kw}")
        jobs = fetch(kw, args.pages, api_key)
        for j in jobs:
            jid = str(j.get("id", ""))
            if jid not in seen_ids:
                seen_ids.add(jid)
                all_jobs.append(j)

    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "findwork_dump.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_jobs, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n{len(all_jobs)} unique jobs saved to {out}")


if __name__ == "__main__":
    main()

# -----------------------------------------------------------------------------
# Gál István – szakdolgozat. A megvalósítás során mesterséges intelligencia (AI) eszközöket használtam.
