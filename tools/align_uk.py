"""Align Ukrainian transcript text to English whisper timestamps.

Maps Ukrainian paragraphs to whisper speech segments, distributes text
proportionally, then calls Claude for word-level alignment.

Usage:
    python -m tools.align_uk \
        --transcript PATH       # transcript_uk.txt (full talk)
        --whisper-json PATH     # Whisper data (per video)
        --output PATH           # uk_whisper.json
        [--batch-size N]        # segments per Claude call (default 20)
        [--skip-word-align]     # skip Claude word-level alignment
"""

import argparse
import json
import re
import subprocess
import sys

from .srt_utils import load_whisper_json

# ---------------------------------------------------------------------------
# Step 1: Parse inputs
# ---------------------------------------------------------------------------


def load_transcript(path):
    """Load transcript text and split into paragraphs.

    Supports both formats:
    - transcript_uk.txt: paragraphs separated by double line breaks (\\n\\n)
    - transcript_en.txt: one paragraph per line (single \\n)

    Strips metadata header (date, location, language lines at the top).
    Returns list of non-empty paragraph strings.
    """
    with open(path, encoding="utf-8") as f:
        text = f.read()

    # Strip metadata header from amruta.org transcript format.
    # Header ends at the "Talk Language:" line (always present in EN transcripts).
    # For UK transcripts (no header), body_start stays at 0.
    lines = text.split("\n")
    body_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"^(Talk Language:|Language:)", stripped):
            body_start = i + 1
            break
        # Stop scanning after first 10 lines — no header found
        if i >= 10:
            break

    body = "\n".join(lines[body_start:])

    # Detect format: if double newlines exist, split on them
    if "\n\n" in body:
        paragraphs = [p.strip() for p in re.split(r"\n\n+", body) if p.strip()]
    else:
        # Single newline per paragraph (transcript_en.txt format)
        paragraphs = [line.strip() for line in body.split("\n") if line.strip()]

    return paragraphs


# ---------------------------------------------------------------------------
# Step 2: Map paragraphs to video segments by time range
# ---------------------------------------------------------------------------


def group_whisper_by_pauses(whisper_segments, n_groups):
    """Group whisper segments into n_groups by finding the largest inter-segment pauses.

    Finds the (n_groups - 1) largest gaps between consecutive whisper segments
    and splits there. This produces groups that align with natural speech pauses.
    """
    if not whisper_segments or n_groups <= 1:
        return [whisper_segments]

    # Calculate gaps between consecutive segments
    gaps = []
    for i in range(1, len(whisper_segments)):
        gap = whisper_segments[i]["start"] - whisper_segments[i - 1]["end"]
        gaps.append((gap, i))

    # Sort by gap size descending, take top (n_groups - 1) split points
    gaps.sort(reverse=True)
    split_indices = sorted(idx for _, idx in gaps[: n_groups - 1])

    # Build groups
    groups = []
    prev = 0
    for idx in split_indices:
        groups.append(whisper_segments[prev:idx])
        prev = idx
    groups.append(whisper_segments[prev:])

    return groups


def map_paragraphs_to_segments(paragraphs, whisper_segments):
    """Map Ukrainian paragraphs to whisper segments.

    Strategy:
    1. Group whisper segments into N groups (N = number of paragraphs)
       by finding the largest natural pauses between segments.
    2. Assign each paragraph to its corresponding segment group.

    Returns list of dicts: {uk_text, segments: [{id, start, end, text, words}]}
    """
    if not paragraphs or not whisper_segments:
        return []

    n_paragraphs = len(paragraphs)

    # Group whisper segments to match paragraph count
    seg_groups = group_whisper_by_pauses(whisper_segments, n_paragraphs)

    # If grouping produced fewer groups (e.g., fewer segments than paragraphs),
    # merge extra paragraphs into the last group's text
    mappings = []
    for i in range(len(seg_groups)):
        uk_text = paragraphs[i] if i < n_paragraphs else ""

        en_text = " ".join(seg.get("text", "") for seg in seg_groups[i])
        mappings.append(
            {
                "uk_text": uk_text,
                "segments": seg_groups[i],
                "en_text": en_text,
            }
        )

    # Handle extra paragraphs beyond the number of groups
    if n_paragraphs > len(seg_groups) and seg_groups:
        extra_text = " ".join(paragraphs[len(seg_groups) :])
        mappings[-1]["uk_text"] += " " + extra_text

    return mappings


# ---------------------------------------------------------------------------
# Step 3: Distribute UK text across segments proportionally
# ---------------------------------------------------------------------------


def distribute_text_to_segments(mappings):
    """Distribute UK text across whisper segments proportionally to EN text length.

    For each mapping (uk_text + segments), splits UK text into segment-sized
    chunks based on the proportion of EN text each segment covers.

    Returns list of segment dicts ready for uk_whisper.json.
    """
    result_segments = []

    for mapping in mappings:
        uk_text = mapping["uk_text"]
        segments = mapping["segments"]

        if not segments:
            continue

        if len(segments) == 1:
            seg = segments[0]
            result_segments.append(
                {
                    "id": seg["id"],
                    "start": seg["start"],
                    "end": seg["end"],
                    "text": uk_text,
                    "words": [],  # to be filled by word alignment
                }
            )
            continue

        # Calculate EN text length per segment
        seg_en_lengths = []
        for seg in segments:
            en_text = seg.get("text", "")
            seg_en_lengths.append(len(en_text.strip()))

        total_en_len = sum(seg_en_lengths) or 1

        # Split UK text proportionally by words using cumulative boundaries
        uk_words = uk_text.split()
        total_uk_words = len(uk_words)

        # Build cumulative proportion boundaries to avoid rounding drift
        cum_proportions = []
        cum = 0.0
        for length in seg_en_lengths:
            cum += length / total_en_len
            cum_proportions.append(cum)

        word_pos = 0
        for i, seg in enumerate(segments):
            if i == len(segments) - 1:
                # Last segment gets remaining words
                seg_words = uk_words[word_pos:]
            else:
                target_end = round(total_uk_words * cum_proportions[i])
                target_end = max(target_end, word_pos + 1)  # at least 1 word
                seg_words = uk_words[word_pos:target_end]
                word_pos = target_end

            seg_text = " ".join(seg_words) if seg_words else ""

            result_segments.append(
                {
                    "id": seg["id"],
                    "start": seg["start"],
                    "end": seg["end"],
                    "text": seg_text,
                    "words": [],
                }
            )

    return result_segments


# ---------------------------------------------------------------------------
# Step 4: Word-level alignment via Claude
# ---------------------------------------------------------------------------


def build_word_alignment_prompt(batch):
    """Build prompt for Claude word-level alignment.

    Each batch item: {uk_text, start, end, en_words: [{start, end, word}]}
    """
    lines = [
        "You are a word-level timestamp aligner. For each segment below, "
        "map Ukrainian words to the English word timestamps. The Ukrainian "
        "text is a translation of the English speech in that time range.",
        "",
        "Rules:",
        "- Every Ukrainian word must get a start and end timestamp",
        "- Timestamps must be within the segment's [start, end] range",
        "- Timestamps must be monotonically increasing",
        "- If one EN word maps to multiple UK words, split its time range",
        "- If multiple EN words map to one UK word, merge their time range",
        "- Output valid JSON only, no commentary",
        "",
        "Output format: a JSON array of segment objects:",
        '[{"id": N, "words": [{"start": F, "end": F, "word": "..."}]}]',
        "",
        "Segments to align:",
        "",
    ]

    for item in batch:
        lines.append(f"Segment {item['id']} [{item['start']:.2f} - {item['end']:.2f}]:")
        lines.append(f"  EN words: {json.dumps(item['en_words'], ensure_ascii=False)}")
        lines.append(f'  UK text: "{item["uk_text"]}"')
        lines.append("")

    return "\n".join(lines)


def call_claude_for_alignment(prompt):
    """Call Claude CLI for word alignment. Returns parsed JSON."""
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            print(f"  Claude CLI error: {result.stderr}", file=sys.stderr)
            return None

        # Extract JSON from response
        response = result.stdout.strip()
        # Try to find JSON array in response
        json_match = re.search(r"\[.*\]", response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return None
    except subprocess.TimeoutExpired:
        print("  Claude CLI timeout", file=sys.stderr)
        return None
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"  Claude alignment error: {e}", file=sys.stderr)
        return None


def align_words(segments, whisper_segments, batch_size=20):
    """Perform word-level alignment using Claude.

    For each segment with UK text and EN whisper words, calls Claude to map
    UK words to EN timestamps.
    """
    # Build lookup: whisper segment id -> words
    whisper_by_id = {}
    for seg in whisper_segments:
        whisper_by_id[seg["id"]] = seg.get("words", [])

    # Build batches
    items_needing_alignment = []
    for seg in segments:
        if not seg["text"]:
            continue
        en_words = whisper_by_id.get(seg["id"], [])
        if not en_words:
            # No word-level data; assign uniform timestamps
            uk_words = seg["text"].split()
            if uk_words:
                dur = seg["end"] - seg["start"]
                step = dur / len(uk_words)
                seg["words"] = [
                    {
                        "start": round(seg["start"] + i * step, 2),
                        "end": round(seg["start"] + (i + 1) * step, 2),
                        "word": w,
                    }
                    for i, w in enumerate(uk_words)
                ]
            continue

        items_needing_alignment.append(
            {
                "id": seg["id"],
                "start": seg["start"],
                "end": seg["end"],
                "uk_text": seg["text"],
                "en_words": en_words,
            }
        )

    # Process in batches
    for i in range(0, len(items_needing_alignment), batch_size):
        batch = items_needing_alignment[i : i + batch_size]
        print(f"  Aligning batch {i // batch_size + 1} ({len(batch)} segments)...", file=sys.stderr)

        prompt = build_word_alignment_prompt(batch)
        result = call_claude_for_alignment(prompt)

        if result:
            # Apply results
            result_by_id = {r["id"]: r["words"] for r in result if "id" in r}
            for item in batch:
                words = result_by_id.get(item["id"])
                if words:
                    # Find corresponding segment and update
                    for seg in segments:
                        if seg["id"] == item["id"]:
                            seg["words"] = words
                            break
        else:
            # Fallback: uniform distribution
            print(f"  Batch {i // batch_size + 1} failed, using uniform distribution", file=sys.stderr)
            for item in batch:
                for seg in segments:
                    if seg["id"] == item["id"]:
                        uk_words = seg["text"].split()
                        if uk_words:
                            dur = seg["end"] - seg["start"]
                            step = dur / len(uk_words)
                            seg["words"] = [
                                {
                                    "start": round(seg["start"] + j * step, 2),
                                    "end": round(seg["start"] + (j + 1) * step, 2),
                                    "word": w,
                                }
                                for j, w in enumerate(uk_words)
                            ]
                        break

    return segments


# ---------------------------------------------------------------------------
# Step 5: Validate and write output
# ---------------------------------------------------------------------------


def validate_segments(segments):
    """Validate aligned segments. Returns list of warnings."""
    warnings = []
    for seg in segments:
        if not seg.get("text"):
            continue
        if not seg.get("words"):
            warnings.append(f"Segment {seg['id']}: no word timestamps")
            continue

        # Check word text matches segment text
        word_text = " ".join(w["word"] for w in seg["words"])
        if word_text != seg["text"]:
            warnings.append(f"Segment {seg['id']}: word text mismatch: '{word_text[:50]}' vs '{seg['text'][:50]}'")

        # Check timestamps in bounds
        for w in seg["words"]:
            if w["start"] < seg["start"] - 0.1:
                warnings.append(f"Segment {seg['id']}: word '{w['word']}' starts before segment")
            if w["end"] > seg["end"] + 0.1:
                warnings.append(f"Segment {seg['id']}: word '{w['word']}' ends after segment")

        # Check monotonicity
        for i in range(1, len(seg["words"])):
            if seg["words"][i]["start"] < seg["words"][i - 1]["start"]:
                warnings.append(f"Segment {seg['id']}: non-monotonic timestamps at word '{seg['words'][i]['word']}'")
                break

    return warnings


def write_uk_whisper(segments, output_path):
    """Write uk_whisper.json output file."""
    output = {
        "language": "uk",
        "segments": segments,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def align(transcript_path, whisper_json_path, output_path, batch_size=20, skip_word_align=False):
    """Run the full alignment pipeline."""
    print(f"Loading transcript: {transcript_path}", file=sys.stderr)
    paragraphs = load_transcript(transcript_path)
    print(f"  {len(paragraphs)} paragraphs", file=sys.stderr)

    print(f"Loading whisper: {whisper_json_path}", file=sys.stderr)
    whisper_segments = load_whisper_json(whisper_json_path)
    print(f"  {len(whisper_segments)} segments", file=sys.stderr)

    # Step 2: Map paragraphs to segments
    print("Mapping paragraphs to whisper segments...", file=sys.stderr)
    mappings = map_paragraphs_to_segments(paragraphs, whisper_segments)
    print(f"  {len(mappings)} paragraph-segment mappings", file=sys.stderr)

    # Step 3: Distribute text
    print("Distributing UK text across segments...", file=sys.stderr)
    segments = distribute_text_to_segments(mappings)
    print(f"  {len(segments)} segments with UK text", file=sys.stderr)

    # Step 4: Word-level alignment
    if not skip_word_align:
        print("Starting word-level alignment...", file=sys.stderr)
        segments = align_words(segments, whisper_segments, batch_size)
    else:
        print("Skipping word-level alignment (--skip-word-align)", file=sys.stderr)
        # Assign uniform timestamps
        for seg in segments:
            uk_words = seg["text"].split() if seg["text"] else []
            if uk_words:
                dur = seg["end"] - seg["start"]
                step = dur / len(uk_words)
                seg["words"] = [
                    {
                        "start": round(seg["start"] + i * step, 2),
                        "end": round(seg["start"] + (i + 1) * step, 2),
                        "word": w,
                    }
                    for i, w in enumerate(uk_words)
                ]

    # Step 5: Validate and write
    print("Validating...", file=sys.stderr)
    warnings = validate_segments(segments)
    if warnings:
        print(f"  {len(warnings)} warnings:", file=sys.stderr)
        for w in warnings[:20]:
            print(f"    {w}", file=sys.stderr)
        if len(warnings) > 20:
            print(f"    ... and {len(warnings) - 20} more", file=sys.stderr)

    write_uk_whisper(segments, output_path)
    print(f"Output written: {output_path} ({len(segments)} segments)", file=sys.stderr)

    return segments


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Align Ukrainian transcript to English whisper timestamps")
    parser.add_argument("--transcript", required=True, help="Path to transcript_uk.txt")
    parser.add_argument("--whisper-json", required=True, help="Path to whisper.json (per video)")
    parser.add_argument("--output", required=True, help="Output uk_whisper.json path")
    parser.add_argument("--batch-size", type=int, default=20, help="Segments per Claude alignment call (default: 20)")
    parser.add_argument(
        "--skip-word-align", action="store_true", help="Skip Claude word-level alignment, use uniform distribution"
    )
    args = parser.parse_args()

    align(
        transcript_path=args.transcript,
        whisper_json_path=args.whisper_json,
        output_path=args.output,
        batch_size=args.batch_size,
        skip_word_align=args.skip_word_align,
    )


if __name__ == "__main__":
    main()
