"""Shared text-segmentation helpers for subtitle tooling.

Previously these lived inside tools/generate_map.py and tools/align_uk.py
and were imported cross-module by sync_transcript_to_srt. Lifting them
here removes the cross-module coupling and gives all transcript-facing
tools one place to go for:

  * load_transcript(path) — strip the metadata header, return the list
    of paragraphs (handles both single-newline and double-newline
    paragraph separators).
  * split_sentences(text) — sentence boundaries at .!? + uppercase,
    with an abbreviation blacklist.
  * split_text_to_lines(text) — recursive splitter that keeps each line
    at or below MAX_CPL characters, preferring good break points
    (punctuation, conjunctions, prepositions).
"""

import re

MAX_CPL = 84

# ---------------------------------------------------------------------------
# Transcript loading
# ---------------------------------------------------------------------------


def load_transcript(path: str) -> list[str]:
    """Load transcript text and split into paragraphs.

    Supports both formats:
    - transcript_uk.txt: paragraphs separated by double line breaks (\\n\\n)
    - transcript_en.txt: one paragraph per line (single \\n)

    Strips metadata header (date, location, language lines at the top).
    Returns list of non-empty paragraph strings.
    """
    with open(path, encoding="utf-8") as f:
        text = f.read()

    lines = text.split("\n")
    body_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"^(Talk Language:|Language:|Мова промови:|Мова:)", stripped):
            body_start = i + 1
            break
        if i >= 10:
            break

    body = "\n".join(lines[body_start:])

    if "\n\n" in body:
        paragraphs = [p.strip() for p in re.split(r"\n\n+", body) if p.strip()]
    else:
        paragraphs = [line.strip() for line in body.split("\n") if line.strip()]

    return paragraphs


# ---------------------------------------------------------------------------
# Sentence splitting
# ---------------------------------------------------------------------------

# Split on .!? followed by space + uppercase, but NOT after abbreviations
_SENT_RE = re.compile(
    r"(?<!Mr\.)(?<!Mrs\.)(?<!Ms\.)(?<!Dr\.)(?<!St\.)(?<!Prof\.)"
    r"(?<!Rev\.)(?<!Jr\.)(?<!Sr\.)(?<!vs\.)(?<!etc\.)(?<!Inc\.)(?<!Ltd\.)"
    r"(?<=[.!?])\s+(?=[A-ZА-ЯІЇЄҐ«\"])"
)


def split_sentences(text: str) -> list[str]:
    """Split text into sentences at .!? followed by uppercase."""
    parts = _SENT_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# Line splitting for ≤ MAX_CPL
# ---------------------------------------------------------------------------

_CONJUNCTIONS = frozenset(
    {
        "що",
        "який",
        "яка",
        "яке",
        "які",
        "і",
        "та",
        "але",
        "бо",
        "тому",
        "коли",
        "де",
        "як",
        "ні",
        "або",
        "чи",
        "адже",
        "проте",
        "однак",
        "якщо",
        "хоча",
    }
)

_PREPOSITIONS = frozenset(
    {
        "в",
        "у",
        "на",
        "з",
        "із",
        "від",
        "до",
        "для",
        "без",
        "через",
        "після",
        "перед",
        "між",
        "під",
        "над",
        "за",
        "при",
        "про",
        "по",
    }
)


def _split_once(text: str) -> list[str]:
    """Find the best single split point for text > MAX_CPL.

    Returns two parts, or [text] if can't split.
    """
    words = text.split()
    if len(words) <= 1:
        return [text]

    mid = len(text) // 2
    candidates: list[tuple[int, int, int]] = []  # (char_pos, priority, distance_from_mid)
    char_pos = 0

    for i, word in enumerate(words[:-1]):
        char_pos += len(word)
        next_word = words[i + 1]
        next_clean = next_word.lower().rstrip(".,;:!?—»\"'")

        if word[-1] in ".!?":
            priority = 1
        elif word[-1] in ",;:" or word.endswith("—"):
            priority = 2
        elif next_clean in _CONJUNCTIONS:
            priority = 3
        elif next_clean in _PREPOSITIONS:
            priority = 4
        else:
            priority = 5

        left_len = char_pos
        right_len = len(text) - char_pos - 1

        if left_len <= MAX_CPL and right_len <= MAX_CPL:
            candidates.append((char_pos, priority, abs(char_pos - mid)))

        char_pos += 1  # space

    if not candidates:
        char_pos = 0
        for word in words[:-1]:
            char_pos += len(word)
            candidates.append((char_pos, 5, abs(char_pos - mid)))
            char_pos += 1

    if not candidates:
        return [text]

    candidates.sort(key=lambda x: (x[1], x[2]))
    split_at = candidates[0][0]
    return [text[:split_at].strip(), text[split_at:].strip()]


def split_text_to_lines(text: str) -> list[str]:
    """Recursively split text into lines of ≤ MAX_CPL characters."""
    if len(text) <= MAX_CPL:
        return [text]
    parts = _split_once(text)
    if len(parts) == 1:
        return parts
    result = []
    for part in parts:
        result.extend(split_text_to_lines(part))
    return result
