"""
Fetches Letterboxd diary entries via rss2json.com proxy API.
Letterboxd blocks GitHub Actions IPs directly, but rss2json
fetches from its own servers (which Letterboxd allows) and
returns JSON we can parse. We paginate month by month using
the diary RSS URL pattern.
"""

import os
import json
import time
import re
import requests
from datetime import datetime

USERNAME = os.environ["LETTERBOXD_USERNAME"]
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")
RSS2JSON_KEY = os.environ.get("RSS2JSON_KEY", "")  # optional, free tier works without
CURRENT_YEAR = datetime.now().year
TMDB_BASE = "https://api.themoviedb.org/3"
POSTER_BASE = "https://image.tmdb.org/t/p/w500"
OUTPUT_PATH = "data/movies.json"


def fetch_poster(title, year):
    if not TMDB_API_KEY:
        return None
    try:
        resp = requests.get(
            f"{TMDB_BASE}/search/movie",
            params={"api_key": TMDB_API_KEY, "query": title, "year": year},
            timeout=10,
        )
        results = resp.json().get("results", [])
        if results and results[0].get("poster_path"):
            return f"{POSTER_BASE}{results[0]['poster_path']}"
    except Exception as e:
        print(f"  TMDB error for '{title}': {e}")
    return None


def fetch_rss_via_proxy(rss_url):
    """Use rss2json.com to fetch and parse an RSS feed."""
    api_url = "https://api.rss2json.com/v1/api.json"
    params = {
        "rss_url": rss_url,
    }
    if RSS2JSON_KEY:
        params["api_key"] = RSS2JSON_KEY
    try:
        resp = requests.get(api_url, params=params, timeout=20)
        print(f"    rss2json status: {resp.status_code}")
        data = resp.json()
        if data.get("status") == "ok":
            return data.get("items", [])
        else:
            print(f"    rss2json error: {data.get('message', 'unknown')}")
    except Exception as e:
        print(f"    Proxy fetch error: {e}")
    return []


def parse_item(item):
    """Convert an rss2json item into our movie dict."""
    # Title format from Letterboxd: "Film Title, 2023 - ★★★½"
    raw_title = item.get("title", "")
    title = re.sub(r"\s*-\s*[★½]+\s*$", "", raw_title).strip()
    title = re.sub(r",\s*\d{4}\s*$", "", title).strip()

    # Watch date
    pub_date = item.get("pubDate", "")
    watched_date = None
    if pub_date:
        try:
            dt = datetime.strptime(pub_date[:10], "%Y-%m-%d")
            watched_date = dt.strftime("%Y-%m-%d")
        except ValueError:
            try:
                dt = datetime.strptime(pub_date[:16].strip(), "%a, %d %b %Y")
                watched_date = dt.strftime("%Y-%m-%d")
            except ValueError:
                pass

    # Release year — Letterboxd puts it in the title after a comma
    year_match = re.search(r",\s*(\d{4})\s*(?:-|$)", raw_title)
    release_year = year_match.group(1) if year_match else None

    # Rating — in the title after " - "
    rating = None
    rating_match = re.search(r"-\s*([★½]+)\s*$", raw_title)
    if rating_match:
        stars_map = {
            "½": 0.5, "★": 1, "★½": 1.5, "★★": 2, "★★½": 2.5,
            "★★★": 3, "★★★½": 3.5, "★★★★": 4, "★★★★½": 4.5, "★★★★★": 5,
        }
        rating = stars_map.get(rating_match.group(1).strip())

    # Letterboxd URL
    letterboxd_url = item.get("link") or item.get("guid") or None

    # Review — strip HTML from description
    description = item.get("description", "") or item.get("content", "") or ""
    review = None
    if description:
        clean = re.sub(r"<[^>]+>", " ", description)
        clean = re.sub(r"\s+", " ", clean).strip()
        clean = re.sub(r"^Watched\s+\w+\s+\d+\.\s*", "", clean).strip()
        if clean and len(clean) > 5:
            review = clean

    return {
        "title": title,
        "release_year": release_year,
        "watched_date": watched_date,
        "rating": rating,
        "poster_url": None,
        "letterboxd_url": letterboxd_url,
        "review": review,
    }


def main():
    os.makedirs("data", exist_ok=True)
    print(f"Fetching @{USERNAME} diary for {CURRENT_YEAR} via rss2json proxy…\n")

    all_movies = []
    now = datetime.now()

    for month in range(1, 13):
        if month > now.month and CURRENT_YEAR == now.year:
            break

        rss_url = f"https://letterboxd.com/{USERNAME}/rss/diary/for/{CURRENT_YEAR}/{month:02d}/"
        print(f"  Month {month:02d}: {rss_url}")

        items = fetch_rss_via_proxy(rss_url)
        print(f"    → {len(items)} items returned")

        for item in items:
            movie = parse_item(item)
            # Only keep entries from this year
            if movie["watched_date"] and movie["watched_date"].startswith(str(CURRENT_YEAR)):
                all_movies.append(movie)

        time.sleep(1)  # respect rss2json rate limits (free tier = 60 req/hour)

    # Deduplicate
    seen = set()
    unique = []
    for m in all_movies:
        key = (m["title"], m["watched_date"])
        if key not in seen:
            seen.add(key)
            unique.append(m)

    print(f"\nTotal unique entries: {len(unique)}")
    print("Fetching posters from TMDB…")

    for m in unique:
        m["poster_url"] = fetch_poster(m["title"], m["release_year"])
        time.sleep(0.25)

    unique.sort(key=lambda m: m["watched_date"] or "", reverse=True)

    payload = {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "year": CURRENT_YEAR,
        "count": len(unique),
        "movies": unique,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"\nDone! {len(unique)} movies saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
