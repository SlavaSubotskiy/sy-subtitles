"""Scan EN transcript for terms not in glossary.

Finds capitalized words, bigrams, and recurring terms that may need
to be added to the glossary for consistent translation.

Usage:
    python -m tools.glossary_check \
        --transcript talks/TALK_ID/transcript_en.txt \
        --glossary glossary/terms_lookup.yaml \
        --report talks/TALK_ID/glossary_candidates.txt
"""

import argparse
import re
from collections import Counter
from pathlib import Path

import yaml

# Common English words that appear capitalized but aren't domain terms
STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "from",
    "up",
    "about",
    "into",
    "through",
    "during",
    "before",
    "after",
    "above",
    "below",
    "between",
    "out",
    "off",
    "over",
    "under",
    "again",
    "further",
    "then",
    "once",
    "here",
    "there",
    "when",
    "where",
    "why",
    "how",
    "all",
    "both",
    "each",
    "few",
    "more",
    "most",
    "other",
    "some",
    "such",
    "no",
    "nor",
    "not",
    "only",
    "own",
    "same",
    "so",
    "than",
    "too",
    "very",
    "can",
    "will",
    "just",
    "should",
    "now",
    "i",
    "you",
    "he",
    "she",
    "it",
    "we",
    "they",
    "me",
    "him",
    "her",
    "us",
    "them",
    "my",
    "your",
    "his",
    "its",
    "our",
    "their",
    "what",
    "which",
    "who",
    "whom",
    "this",
    "that",
    "these",
    "those",
    "am",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "having",
    "do",
    "does",
    "did",
    "doing",
    "would",
    "could",
    "might",
    "must",
    "shall",
    "may",
    "need",
    "also",
    "even",
    "still",
    "already",
    "yet",
    "if",
    "because",
    "as",
    "until",
    "while",
    "although",
    "though",
    "god",
    "mother",
    "father",
    "people",
    "one",
    "two",
    "three",
    "first",
    "second",
    "third",
    "new",
    "old",
    "great",
    "good",
    "bad",
    "many",
    "much",
    "little",
    "big",
    "small",
    "long",
    "short",
    "high",
    "low",
    "every",
    "last",
    "next",
    "another",
    "say",
    "said",
    "know",
    "think",
    "see",
    "come",
    "make",
    "like",
    "time",
    "way",
    "thing",
    "man",
    "woman",
    "child",
    "world",
    "life",
    "day",
    "year",
    "work",
    "part",
    "place",
    "case",
    "point",
    "hand",
    "right",
    "left",
    "india",
    "english",
    "indian",
    "america",
    "american",
    "europe",
    "european",
    "london",
    "today",
    "yesterday",
    "tomorrow",
}


def load_glossary_terms(glossary_path):
    """Load all EN terms from glossary, return normalized set."""
    with open(glossary_path, encoding="utf-8") as f:
        entries = yaml.safe_load(f) or []
    terms = set()
    for entry in entries:
        en = entry.get("en", "")
        for variant in en.split("/"):
            term = variant.strip().lower()
            if term:
                terms.add(term)
                # Also add individual words for multi-word terms
                for word in term.split():
                    terms.add(word)
    return terms


def extract_candidates(text, known_terms):
    """Extract candidate terms from EN transcript."""
    # Find capitalized words not at sentence start
    sentences = re.split(r"[.!?]+\s+", text)
    candidates = Counter()

    for sentence in sentences:
        words = sentence.split()
        for i, word in enumerate(words):
            clean = re.sub(r"[^a-zA-Z'-]", "", word)
            if not clean or len(clean) < 3:
                continue
            if clean[0].isupper() and i > 0:  # Not sentence start
                lower = clean.lower()
                if lower not in STOPWORDS and lower not in known_terms:
                    candidates[clean] += 1

            # Check bigrams (two consecutive capitalized words)
            if i > 0 and i < len(words) - 1:
                next_clean = re.sub(r"[^a-zA-Z'-]", "", words[i + 1])
                if clean[0].isupper() and next_clean and next_clean[0].isupper():
                    bigram = f"{clean} {next_clean}"
                    bigram_lower = bigram.lower()
                    if bigram_lower not in known_terms:
                        candidates[bigram] += 1

    # Filter: keep only terms appearing 2+ times
    return {term: count for term, count in candidates.items() if count >= 2}


def generate_report(talk_id, candidates):
    """Generate a report of glossary candidates."""
    lines = [
        f"GLOSSARY CANDIDATES — {talk_id}",
        "=" * 60,
    ]
    if not candidates:
        lines.append("No new candidate terms found.")
        return "\n".join(lines) + "\n"

    sorted_candidates = sorted(candidates.items(), key=lambda x: -x[1])
    lines.append(f"Found {len(sorted_candidates)} terms not in glossary (appearing 2+ times):")
    lines.append("")
    for term, count in sorted_candidates:
        lines.append(f"  {term:<30} ({count} occurrences)")
    lines.append("")
    lines.append("To add a term, append to glossary/terms_lookup.yaml:")
    lines.append("- en: <English term>")
    lines.append("  uk: <Ukrainian translation>")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Scan EN transcript for glossary candidates")
    parser.add_argument("--transcript", required=True, help="Path to transcript_en.txt")
    parser.add_argument("--glossary", required=True, help="Path to terms_lookup.yaml")
    parser.add_argument("--report", required=True, help="Output report path")
    args = parser.parse_args()

    transcript = Path(args.transcript).read_text(encoding="utf-8")
    known = load_glossary_terms(args.glossary)

    # Extract talk_id from path
    talk_id = Path(args.transcript).parent.name

    candidates = extract_candidates(transcript, known)
    report = generate_report(talk_id, candidates)

    Path(args.report).write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
