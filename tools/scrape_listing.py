"""Scrape all Ukrainian-translated talk links from amruta.org listing page.

Fetches the chronological listing page, extracts talk URLs with dates/slugs,
derives EN URLs, and saves an index for the transcript fetcher.

Usage:
    python -m tools.scrape_listing [--output glossary/corpus/index.yaml] [--cookie ...]
"""

import argparse
import os
import re
from datetime import date

import yaml

from tools.download import AmrutaDownloader

LISTING_URL = "https://www.amruta.org/uk/all-shri-mataji-talks-in-chronological-order/"

# Pattern: /uk/YYYY/MM/DD/slug/ (with optional trailing slash)
UK_TALK_RE = re.compile(r"https?://www\.amruta\.org/uk/(\d{4})/(\d{2})/(\d{2})/([\w-]+)/?$")


def scrape_listing_page(downloader, url):
    """Scrape a single listing page, return (entries, next_page_url)."""
    soup = downloader.fetch_talk_page(url)

    entries = []
    content = soup.find("div", class_="entry-content")
    if not content:
        print(f"  Warning: no entry-content found on {url}")
        return entries, None

    for a in content.find_all("a", href=True):
        href = a["href"].rstrip("/") + "/"
        m = UK_TALK_RE.match(href)
        if not m:
            continue

        year, month, day, slug = m.groups()
        talk_date = f"{year}-{month}-{day}"
        title = a.get_text(strip=True)
        uk_url = href
        en_url = uk_url.replace("/uk/", "/", 1)

        entries.append(
            {
                "slug": slug,
                "date": talk_date,
                "title": title,
                "uk_url": uk_url,
                "en_url": en_url,
            }
        )

    # Check for pagination
    next_url = None
    next_link = soup.find("a", class_="next")
    if not next_link:
        next_link = soup.find("a", string=re.compile(r"Next|Далі|→|›"))
    if next_link and next_link.get("href"):
        next_url = next_link["href"]

    return entries, next_url


def scrape_all(downloader, start_url=LISTING_URL):
    """Scrape all pages of the listing, return combined entries."""
    all_entries = []
    seen_slugs = set()
    url = start_url
    page = 1

    while url:
        print(f"Scraping page {page}: {url}")
        entries, next_url = scrape_listing_page(downloader, url)
        new = 0
        for entry in entries:
            if entry["slug"] not in seen_slugs:
                seen_slugs.add(entry["slug"])
                all_entries.append(entry)
                new += 1
        print(f"  Found {len(entries)} links, {new} new (total: {len(all_entries)})")
        url = next_url
        page += 1

    return all_entries


def save_index(entries, output_path):
    """Save entries to index.yaml."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    header = f"# Scraped: {date.today().isoformat()}\n"

    # Use clean list-of-dicts format
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header)
        yaml.dump(
            entries,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )

    print(f"\nSaved {len(entries)} entries to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Scrape amruta.org UK talk listing into index.yaml")
    parser.add_argument(
        "--output",
        default="glossary/corpus/index.yaml",
        help="Output index file (default: glossary/corpus/index.yaml)",
    )
    parser.add_argument("--cookie", help="Session cookie (overrides env)")
    parser.add_argument(
        "--url",
        default=LISTING_URL,
        help="Listing page URL (default: chronological UK talks)",
    )
    args = parser.parse_args()

    downloader = AmrutaDownloader(session_cookie=args.cookie)
    entries = scrape_all(downloader, start_url=args.url)

    if entries:
        save_index(entries, args.output)
    else:
        print("No entries found. Check cookie / URL.")


if __name__ == "__main__":
    main()
