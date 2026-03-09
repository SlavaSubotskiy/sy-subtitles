"""Generate initial uk.map from EN + UK transcripts, EN SRT, and whisper.json.

Uses paragraph-level alignment (EN and UK transcripts have equal paragraph
count) to assign precise time ranges, then splits into subtitle-sized lines.

The builder agent then reviews and corrects semantic timing — this tool only
does mechanical splitting and proportional time assignment.

Usage:
    python -m tools.generate_map \
        --transcript PATH \
        --transcript-en PATH \
        --en-srt PATH \
        --whisper-json PATH \
        --output PATH
"""

import argparse
import re
import sys

from .align_uk import load_transcript
from .srt_utils import load_whisper_json, ms_to_time, parse_srt

MAX_CPL = 84

# ---------------------------------------------------------------------------
# Sentence splitting
# ---------------------------------------------------------------------------

# Split on .!? followed by space + uppercase, but NOT after abbreviations
_SENT_RE = re.compile(
    r"(?<!Mr\.)(?<!Mrs\.)(?<!Ms\.)(?<!Dr\.)(?<!St\.)(?<!Prof\.)"
    r"(?<!Rev\.)(?<!Jr\.)(?<!Sr\.)(?<!vs\.)(?<!etc\.)(?<!Inc\.)(?<!Ltd\.)"
    r"(?<=[.!?])\s+(?=[A-ZА-ЯІЇЄҐ«\"])"
)


def split_sentences(text):
    """Split text into sentences at .!? followed by uppercase."""
    parts = _SENT_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# Text splitting for ≤ MAX_CPL
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


def _split_once(text):
    """Find the best single split point for text > MAX_CPL.

    Returns two parts, or [text] if can't split.
    """
    words = text.split()
    if len(words) <= 1:
        return [text]

    mid = len(text) // 2
    candidates = []  # (char_pos, priority, distance_from_mid)
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


def split_text_to_lines(text):
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


# ---------------------------------------------------------------------------
# Whisper word extraction
# ---------------------------------------------------------------------------


def _find_words_for_block(block, segments):
    """Find whisper words overlapping with an EN block's time range."""
    start_s = block["start_ms"] / 1000
    end_s = block["end_ms"] / 1000
    words = []
    for seg in segments:
        if seg["end"] < start_s - 1:
            continue
        if seg["start"] > end_s + 1:
            break
        for w in seg.get("words", []):
            if w["end"] >= start_s and w["start"] <= end_s:
                words.append(w)
    return words


def _get_group_words(en_blocks, whisper_segments):
    """Get all whisper words for a group of EN blocks, deduplicated and sorted."""
    all_words = []
    seen = set()
    for block in en_blocks:
        for w in _find_words_for_block(block, whisper_segments):
            key = (round(w["start"], 3), round(w["end"], 3))
            if key not in seen:
                seen.add(key)
                all_words.append(w)
    return sorted(all_words, key=lambda w: w["start"])


# ---------------------------------------------------------------------------
# Paragraph → EN block assignment (using EN transcript text)
# ---------------------------------------------------------------------------


def assign_blocks_to_paragraphs(en_paragraphs, en_blocks):
    """Assign EN SRT blocks to EN paragraphs by cumulative word count.

    Since EN transcript and EN SRT contain the same speech text,
    we use word count proportions to map blocks to paragraphs.
    """
    para_words = [len(p.split()) for p in en_paragraphs]
    block_words = [len(b["text"].split()) for b in en_blocks]

    total_para = sum(para_words)
    total_block = sum(block_words)

    if total_para == 0 or total_block == 0:
        return [en_blocks] + [[] for _ in en_paragraphs[1:]]

    # Paragraph boundaries in block-word-count space
    scale = total_block / total_para
    para_end = []
    cum = 0
    for pw in para_words:
        cum += pw
        para_end.append(cum * scale)

    # Greedily assign blocks to paragraphs
    groups = [[] for _ in en_paragraphs]
    cum_words = 0
    para_idx = 0

    for b_idx, bw in enumerate(block_words):
        groups[para_idx].append(en_blocks[b_idx])
        cum_words += bw

        if para_idx < len(para_end) - 1 and cum_words >= para_end[para_idx]:
            para_idx += 1

    return groups


# ---------------------------------------------------------------------------
# EN sentence time ranges (within a paragraph group)
# ---------------------------------------------------------------------------


def _sentence_times_from_words(sentences, whisper_words):
    """Distribute whisper words across sentences by EN word count proportion.

    Returns list of (start_ms, end_ms) per sentence.
    """
    if not whisper_words:
        return [(0, 0)] * len(sentences)

    word_counts = [len(s.split()) for s in sentences]
    total_sent = sum(word_counts)
    total_whisper = len(whisper_words)
    scale = total_whisper / max(total_sent, 1)

    times = []
    w_idx = 0
    for i, wc in enumerate(word_counts):
        scaled = max(1, round(wc * scale))
        if i == len(word_counts) - 1:
            end_idx = total_whisper - 1
        else:
            end_idx = min(w_idx + scaled - 1, total_whisper - 1)
            end_idx = max(end_idx, w_idx)

        start_ms = int(round(whisper_words[w_idx]["start"] * 1000))
        end_ms = int(round(whisper_words[end_idx]["end"] * 1000))
        if start_ms >= end_ms:
            end_ms = start_ms + 100

        times.append((start_ms, end_ms))
        w_idx = min(end_idx + 1, total_whisper - 1)

    return times


# ---------------------------------------------------------------------------
# Time distribution helpers
# ---------------------------------------------------------------------------


def _distribute_times_proportional(whisper_words, char_counts):
    """Distribute whisper words across parts by character count proportion."""
    n = len(char_counts)
    total_chars = sum(char_counts)

    if not whisper_words or total_chars == 0:
        return [(0, 0)] * n

    total_words = len(whisper_words)
    cum_prop = []
    cum = 0.0
    for cc in char_counts:
        cum += cc / total_chars
        cum_prop.append(cum)

    result = []
    word_pos = 0
    for i in range(n):
        if i == n - 1:
            end_idx = total_words - 1
        else:
            target = round(total_words * cum_prop[i])
            end_idx = max(target - 1, word_pos)
            end_idx = min(end_idx, total_words - 1)

        start_ms = int(round(whisper_words[word_pos]["start"] * 1000))
        end_ms = int(round(whisper_words[end_idx]["end"] * 1000))
        if start_ms >= end_ms:
            end_ms = start_ms + 100

        result.append((start_ms, end_ms))
        word_pos = min(end_idx + 1, total_words - 1)

    return result


def _distribute_in_range(start_ms, end_ms, char_counts):
    """Distribute a fixed time range across parts by character proportion."""
    total = sum(char_counts)
    if total == 0:
        return [(start_ms, end_ms)] * len(char_counts)

    dur = end_ms - start_ms
    result = []
    t = start_ms
    for i, cc in enumerate(char_counts):
        if i == len(char_counts) - 1:
            result.append((t, end_ms))
        else:
            d = max(1, round(dur * cc / total))
            result.append((t, t + d))
            t += d
    return result


# ---------------------------------------------------------------------------
# Main generation
# ---------------------------------------------------------------------------


def generate_map(
    transcript_uk_path,
    transcript_en_path,
    en_srt_path,
    whisper_json_path,
    output_path,
):
    """Generate uk.map mapping table."""
    uk_paragraphs = load_transcript(transcript_uk_path)
    en_paragraphs = load_transcript(transcript_en_path)
    en_blocks = parse_srt(en_srt_path)
    whisper_segments = load_whisper_json(whisper_json_path)

    print(f"UK paragraphs: {len(uk_paragraphs)}", file=sys.stderr)
    print(f"EN paragraphs: {len(en_paragraphs)}", file=sys.stderr)
    print(f"EN SRT blocks: {len(en_blocks)}", file=sys.stderr)

    if len(uk_paragraphs) != len(en_paragraphs):
        print(
            f"WARNING: paragraph count mismatch! UK={len(uk_paragraphs)}, EN={len(en_paragraphs)}",
            file=sys.stderr,
        )

    # Step 1: Assign EN blocks to EN paragraphs by text proportion
    groups = assign_blocks_to_paragraphs(en_paragraphs, en_blocks)
    print(
        f"Block groups: {len(groups)} (blocks per group: "
        f"{', '.join(str(len(g)) for g in groups[:5])}{'...' if len(groups) > 5 else ''})",
        file=sys.stderr,
    )

    # Step 2: Build mapping
    map_lines = []
    block_num = 1
    stats = {"sentence_match": 0, "proportional": 0}

    n_paras = min(len(uk_paragraphs), len(groups))
    for p_idx in range(n_paras):
        uk_para = uk_paragraphs[p_idx]
        en_para = en_paragraphs[p_idx] if p_idx < len(en_paragraphs) else ""
        en_group = groups[p_idx]

        if not en_group:
            print(f"  WARNING: P{p_idx + 1} has no EN blocks", file=sys.stderr)
            continue

        words = _get_group_words(en_group, whisper_segments)

        # Split into sentences
        uk_sentences = split_sentences(uk_para)
        en_sentences = split_sentences(en_para)

        if len(uk_sentences) == len(en_sentences) and len(uk_sentences) > 1 and words:
            # Sentence counts match — sentence-level alignment
            stats["sentence_match"] += 1
            sent_times = _sentence_times_from_words(en_sentences, words)

            if len(sent_times) != len(uk_sentences):
                # Edge case fallback
                sent_times = _distribute_times_proportional(words, [len(s) for s in uk_sentences])

            for uk_sent, (s_start, s_end) in zip(uk_sentences, sent_times, strict=True):
                lines = split_text_to_lines(uk_sent)
                if len(lines) == 1:
                    map_lines.append(f"{block_num} | {ms_to_time(s_start)} | {ms_to_time(s_end)} | {lines[0]}")
                    block_num += 1
                else:
                    times = _distribute_in_range(s_start, s_end, [len(ln) for ln in lines])
                    for line, (ts, te) in zip(lines, times, strict=True):
                        map_lines.append(f"{block_num} | {ms_to_time(ts)} | {ms_to_time(te)} | {line}")
                        block_num += 1
        else:
            # Different sentence counts or single sentence — proportional
            stats["proportional"] += 1
            lines = split_text_to_lines(uk_para)

            if words:
                times = _distribute_times_proportional(words, [len(ln) for ln in lines])
                for line, (ts, te) in zip(lines, times, strict=True):
                    map_lines.append(f"{block_num} | {ms_to_time(ts)} | {ms_to_time(te)} | {line}")
                    block_num += 1
            else:
                s_ms = en_group[0]["start_ms"]
                e_ms = en_group[-1]["end_ms"]
                times = _distribute_in_range(s_ms, e_ms, [len(ln) for ln in lines])
                for line, (ts, te) in zip(lines, times, strict=True):
                    map_lines.append(f"{block_num} | {ms_to_time(ts)} | {ms_to_time(te)} | {line}")
                    block_num += 1

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(map_lines) + "\n")

    total = block_num - 1
    print(f"Generated: {total} mapping lines", file=sys.stderr)
    print(f"  Sentence-matched: {stats['sentence_match']} paragraphs", file=sys.stderr)
    print(f"  Proportional: {stats['proportional']} paragraphs", file=sys.stderr)
    print(f"Output: {output_path}", file=sys.stderr)
    return total


def main():
    parser = argparse.ArgumentParser(description="Generate initial uk.map from transcripts + EN SRT + whisper")
    parser.add_argument("--transcript", required=True, help="Path to transcript_uk.txt")
    parser.add_argument("--transcript-en", required=True, help="Path to transcript_en.txt")
    parser.add_argument("--en-srt", required=True, help="Path to EN SRT file")
    parser.add_argument("--whisper-json", required=True, help="Path to whisper.json")
    parser.add_argument("--output", required=True, help="Output uk.map path")
    args = parser.parse_args()

    generate_map(
        args.transcript,
        args.transcript_en,
        args.en_srt,
        args.whisper_json,
        args.output,
    )


if __name__ == "__main__":
    main()
