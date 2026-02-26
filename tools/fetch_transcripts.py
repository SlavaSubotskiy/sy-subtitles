"""Fetch EN + UK transcript text for talks listed in the corpus index.

Reads index.yaml, fetches each talk page, extracts transcript text
via AmrutaDownloader.extract_transcript(), and saves to per-slug directories.
Resumable: skips slugs where both en.txt and uk.txt already exist.

Usage:
    python -m tools.fetch_transcripts [--index glossary/corpus/index.yaml] \
        [--slug SLUG] [--delay 2] [--cookie ...]
"""

import argparse
import os
import time

import yaml

from tools.download import AmrutaDownloader

SENTINEL_CONTENT = ""  # empty file = 404 sentinel


def load_index(index_path):
    """Load index.yaml, return list of talk entries."""
    with open(index_path, encoding="utf-8") as f:
        entries = yaml.safe_load(f)
    if not entries:
        return []
    return entries


def is_complete(corpus_dir, slug):
    """Check if both en.txt and uk.txt exist for a slug."""
    slug_dir = os.path.join(corpus_dir, slug)
    en_path = os.path.join(slug_dir, "en.txt")
    uk_path = os.path.join(slug_dir, "uk.txt")
    return os.path.exists(en_path) and os.path.exists(uk_path)


def fetch_and_save(downloader, url, output_path, label):
    """Fetch a single transcript page and save text.

    Returns: 'ok', 'empty', '404', or 'error'.
    """
    try:
        soup = downloader.fetch_talk_page(url)
    except Exception as e:
        error_str = str(e)
        if "404" in error_str:
            # Write empty sentinel so we don't retry
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(SENTINEL_CONTENT)
            print(f"    {label}: 404 (sentinel written)")
            return "404"
        print(f"    {label}: ERROR {e}")
        return "error"

    text = downloader.extract_transcript(soup)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if not text:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(SENTINEL_CONTENT)
        print(f"    {label}: no transcript found (sentinel written)")
        return "empty"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)

    if len(text) < 200:
        print(f"    {label}: WARNING — only {len(text)} chars (cookie expired?)")
    else:
        print(f"    {label}: {len(text)} chars")

    return "ok"


def fetch_transcripts(downloader, entries, corpus_dir, delay=2.0, slug_filter=None):
    """Fetch transcripts for all entries. Resumable and rate-limited."""
    stats = {"skipped": 0, "ok": 0, "error": 0, "total": len(entries)}

    for i, entry in enumerate(entries, 1):
        slug = entry["slug"]

        if slug_filter and slug != slug_filter:
            continue

        if is_complete(corpus_dir, slug):
            stats["skipped"] += 1
            continue

        print(f"[{i}/{stats['total']}] {slug}")
        slug_dir = os.path.join(corpus_dir, slug)

        en_path = os.path.join(slug_dir, "en.txt")
        uk_path = os.path.join(slug_dir, "uk.txt")

        # Fetch EN
        en_ok = True
        if not os.path.exists(en_path):
            result = fetch_and_save(downloader, entry["en_url"], en_path, "EN")
            if result == "error":
                en_ok = False
            if result != "error":
                time.sleep(delay)

        # Fetch UK
        if not os.path.exists(uk_path):
            result = fetch_and_save(downloader, entry["uk_url"], uk_path, "UK")
            if result == "error" or not en_ok:
                stats["error"] += 1
            else:
                stats["ok"] += 1
            if result != "error":
                time.sleep(delay)
        else:
            if en_ok:
                stats["ok"] += 1
            else:
                stats["error"] += 1

    print(f"\nDone: {stats['ok']} fetched, {stats['skipped']} skipped, {stats['error']} errors, {stats['total']} total")


def main():
    parser = argparse.ArgumentParser(description="Fetch EN+UK transcripts for talks in the corpus index")
    parser.add_argument(
        "--index",
        default="glossary/corpus/index.yaml",
        help="Path to index.yaml (default: glossary/corpus/index.yaml)",
    )
    parser.add_argument(
        "--slug",
        help="Fetch only this slug (for testing / single talk)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay between requests in seconds (default: 2)",
    )
    parser.add_argument("--cookie", help="Session cookie (overrides env)")
    args = parser.parse_args()

    corpus_dir = os.path.dirname(args.index)

    downloader = AmrutaDownloader(session_cookie=args.cookie)
    entries = load_index(args.index)
    if not entries:
        print(f"No entries in {args.index}")
        return

    print(f"Loaded {len(entries)} talks from {args.index}")
    fetch_transcripts(
        downloader,
        entries,
        corpus_dir,
        delay=args.delay,
        slug_filter=args.slug,
    )


if __name__ == "__main__":
    main()
