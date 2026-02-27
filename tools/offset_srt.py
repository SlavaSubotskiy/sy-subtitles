"""Detect time offset between two EN SRTs and apply it to a UK SRT."""

import argparse
import re
import sys
from difflib import SequenceMatcher

from .srt_utils import parse_srt, write_srt


def normalize_text(text):
    """Normalize text for comparison: lowercase, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def text_similarity(t1, t2):
    """Compute similarity ratio between two texts (0.0 to 1.0)."""
    return SequenceMatcher(None, t1, t2).ratio()


def detect_offset(srt1_path, srt2_path, check_blocks=10, tolerance_ms=500, similarity_threshold=0.98):
    """Detect constant time offset between two SRT files with near-identical text.

    Texts are considered matching if similarity >= similarity_threshold.
    Offset consistency is checked across first check_blocks with tolerance_ms.
    Returns offset_ms (srt2 - srt1) or None if texts differ or offset is inconsistent.
    """
    blocks1 = parse_srt(srt1_path)
    blocks2 = parse_srt(srt2_path)

    if not blocks1 or not blocks2:
        print("ERROR: One or both SRT files are empty", file=sys.stderr)
        return None

    if len(blocks1) != len(blocks2):
        print(
            f"DIFFERENT: Block count mismatch ({len(blocks1)} vs {len(blocks2)})",
            file=sys.stderr,
        )
        return None

    # Compare full text (joined) using similarity
    text1 = normalize_text(" ".join(b["text"] for b in blocks1))
    text2 = normalize_text(" ".join(b["text"] for b in blocks2))
    sim = text_similarity(text1, text2)

    if sim < similarity_threshold:
        print(
            f"DIFFERENT: Text similarity {sim:.4f} < {similarity_threshold}",
            file=sys.stderr,
        )
        return None

    print(f"Text similarity: {sim:.4f}", file=sys.stderr)

    # Compute offset from first block
    offset_ms = blocks2[0]["start_ms"] - blocks1[0]["start_ms"]

    # Verify consistency across first N blocks
    n = min(check_blocks, len(blocks1), len(blocks2))
    for i in range(n):
        block_offset = blocks2[i]["start_ms"] - blocks1[i]["start_ms"]
        if abs(block_offset - offset_ms) > tolerance_ms:
            print(
                f"INCONSISTENT: Block {i+1} offset {block_offset}ms " f"differs from expected {offset_ms}ms",
                file=sys.stderr,
            )
            return None

    return offset_ms


def apply_offset(srt_path, offset_ms, output_path):
    """Apply a time offset to all blocks in an SRT file."""
    blocks = parse_srt(srt_path)

    for b in blocks:
        b["start_ms"] += offset_ms
        b["end_ms"] += offset_ms

    write_srt(blocks, output_path)
    print(f"Written {len(blocks)} blocks to {output_path} (offset: {offset_ms:+d}ms)")


def main():
    parser = argparse.ArgumentParser(description="SRT offset detection and application")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # detect subcommand
    detect_parser = subparsers.add_parser("detect", help="Detect offset between two EN SRTs")
    detect_parser.add_argument("--srt1", required=True, help="First (reference) SRT file")
    detect_parser.add_argument("--srt2", required=True, help="Second SRT file")

    # apply subcommand
    apply_parser = subparsers.add_parser("apply", help="Apply offset to an SRT file")
    apply_parser.add_argument("--srt", required=True, help="Input SRT file")
    apply_parser.add_argument("--offset-ms", required=True, type=int, help="Offset in milliseconds")
    apply_parser.add_argument("--output", required=True, help="Output SRT file path")

    args = parser.parse_args()

    if args.command == "detect":
        offset = detect_offset(args.srt1, args.srt2)
        if offset is not None:
            sign = "+" if offset >= 0 else ""
            seconds = offset / 1000
            print(f"OFFSET: {offset}ms ({sign}{seconds:.3f}s)")
            print(f"  srt2 = srt1 {sign}{seconds:.3f}s")
        else:
            sys.exit(1)

    elif args.command == "apply":
        apply_offset(args.srt, args.offset_ms, args.output)


if __name__ == "__main__":
    main()
