"""Query EN SRT blocks with whisper word timestamps for subtitle builder agent.

Provides on-demand access to EN blocks with word-level timing in SRT format,
so the builder agent can directly use the timecodes without conversion.

Usage:
    # Block count and time range
    python -m tools.builder_data info --en-srt PATH --whisper-json PATH

    # Blocks in range with word timestamps (SRT-formatted)
    python -m tools.builder_data query --en-srt PATH --whisper-json PATH --from 1 --to 50

    # Find blocks by English text
    python -m tools.builder_data search --en-srt PATH --whisper-json PATH --text "Shri Ganesha"
"""

import argparse

from .srt_utils import load_whisper_json, ms_to_time, parse_srt


def _seconds_to_tc(s):
    """Convert float seconds to SRT timecode HH:MM:SS,mmm."""
    return ms_to_time(int(round(s * 1000)))


def _load(args):
    """Load and return (en_blocks, whisper_segments)."""
    blocks = parse_srt(args.en_srt)
    segments = load_whisper_json(args.whisper_json)
    return blocks, segments


def _find_words_for_block(block, segments):
    """Find whisper words that overlap with an EN SRT block's time range."""
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


def _format_block(block, segments):
    """Format one block with whisper word timestamps in SRT timecode format.

    Timing line shows pure speech range:
    - start = first word start
    - end = last word end
    Padding is applied later by build_srt.py.
    """
    words = _find_words_for_block(block, segments)
    lines = []

    if words:
        speech_start_ms = int(round(words[0]["start"] * 1000))
        speech_end_ms = int(round(words[-1]["end"] * 1000))

        lines.append(f"=== #{block['idx']} ===")
        lines.append(f"Text: {block['text']}")
        lines.append(f"Timing: {ms_to_time(speech_start_ms)} → {ms_to_time(speech_end_ms)}")

        # Word timestamps with start→end — pipe-separated
        word_parts = []
        for w in words:
            w_start = _seconds_to_tc(w["start"])
            w_end = _seconds_to_tc(w["end"])
            word_parts.append(f"{w['word']} {w_start}→{w_end}")
        lines.append(f"Words: {' | '.join(word_parts)}")
    else:
        # No whisper words found — show EN SRT timing as fallback
        srt_start = ms_to_time(block["start_ms"])
        srt_end = ms_to_time(block["end_ms"])
        lines.append(f"=== #{block['idx']} ===")
        lines.append(f"Text: {block['text']}")
        lines.append(f"Timing: {srt_start} → {srt_end} (EN SRT, no whisper words)")

    return lines


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_info(args):
    blocks, segments = _load(args)
    srt_start = ms_to_time(blocks[0]["start_ms"])
    srt_end = ms_to_time(blocks[-1]["end_ms"])
    total_words = sum(len(s.get("words", [])) for s in segments)
    print(f"{len(blocks)} EN blocks ({srt_start} — {srt_end}), {total_words} whisper words")


def cmd_query(args):
    blocks, segments = _load(args)
    from_idx = args.from_block or 1
    to_idx = args.to_block or len(blocks)
    from_idx = max(1, from_idx)
    to_idx = min(len(blocks), to_idx)

    selected = [b for b in blocks if from_idx <= b["idx"] <= to_idx]

    for block in selected:
        for line in _format_block(block, segments):
            print(line)
        print()


def cmd_search(args):
    blocks, segments = _load(args)
    query = args.text.lower()

    for block in blocks:
        if query in block["text"].lower():
            for line in _format_block(block, segments):
                print(line)
            print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    # Common args shared by all subcommands
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--en-srt", required=True, help="Path to EN SRT file")
    common.add_argument("--whisper-json", required=True, help="Path to whisper.json file")

    parser = argparse.ArgumentParser(description="Query EN SRT blocks with whisper word timestamps")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("info", parents=[common], help="Block count and time range")

    q = sub.add_parser("query", parents=[common], help="Blocks in range")
    q.add_argument("--from", type=int, dest="from_block", help="Start block number")
    q.add_argument("--to", type=int, dest="to_block", help="End block number")

    s = sub.add_parser("search", parents=[common], help="Find blocks by text")
    s.add_argument("--text", required=True, help="Text to search for")

    args = parser.parse_args()

    commands = {"info": cmd_info, "query": cmd_query, "search": cmd_search}
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
