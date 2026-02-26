"""Extract SRT subtitle text for language review.

Outputs blocks in [N] text format for use with the 5-agent review process.

Usage:
    python -m tools.extract_review --srt PATH [--output PATH]

Without --output, prints to stdout.
"""

import argparse
import sys

from .srt_utils import parse_srt


def extract_review_text(blocks):
    """Convert SRT blocks to review format: [N] text."""
    lines = []
    for b in blocks:
        text = b["text"].replace("\n", " ")
        lines.append(f"[{b['idx']}] {text}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Extract SRT text for language review")
    parser.add_argument("--srt", required=True, help="Input SRT file")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    args = parser.parse_args()

    blocks = parse_srt(args.srt)
    text = extract_review_text(blocks)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
            f.write("\n")
        print(f"Extracted {len(blocks)} blocks to {args.output}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
