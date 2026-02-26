"""Export SRT subtitles to plain text transcript.

Joins subtitle blocks into paragraphs, splitting on pauses > 2 seconds.

Usage:
    python -m tools.text_export --srt PATH --meta PATH --output PATH
    python -m tools.text_export --srt PATH --output PATH --double-spacing
"""

import argparse

import yaml

from .srt_utils import parse_srt


def srt_to_text(blocks, pause_threshold_ms=2000, double_spacing=False):
    """Convert SRT blocks to plain text paragraphs.

    Splits into new paragraph when gap between blocks exceeds pause_threshold_ms.
    When double_spacing is True, separates paragraphs with \\n\\n (for transcript_uk.txt).
    When False, separates with \\n (for transcript_en.txt compatibility).
    """
    if not blocks:
        return ""

    paragraphs = []
    current = [blocks[0]["text"].replace("\n", " ")]

    for i in range(1, len(blocks)):
        gap = blocks[i]["start_ms"] - blocks[i - 1]["end_ms"]
        if gap > pause_threshold_ms:
            paragraphs.append(" ".join(current))
            current = []
        current.append(blocks[i]["text"].replace("\n", " "))

    if current:
        paragraphs.append(" ".join(current))

    separator = "\n\n" if double_spacing else "\n"
    return separator.join(paragraphs)


def export(srt_path, output_path, meta_path=None, double_spacing=False):
    """Export SRT to plain text with optional metadata header."""
    blocks = parse_srt(srt_path)

    header_lines = []
    if meta_path:
        with open(meta_path, encoding="utf-8") as f:
            meta = yaml.safe_load(f)
        if meta:
            if meta.get("title"):
                header_lines.append(meta["title"])
            parts = []
            if meta.get("date"):
                parts.append(str(meta["date"]))
            if meta.get("location"):
                parts.append(meta["location"])
            if parts:
                header_lines.append(", ".join(parts))
            if meta.get("language"):
                header_lines.append(f"Language: {meta['language']}")

    text = srt_to_text(blocks, double_spacing=double_spacing)

    with open(output_path, "w", encoding="utf-8") as f:
        if header_lines:
            for line in header_lines:
                f.write(line + "\n")
            f.write("\n")
        f.write(text)
        f.write("\n")

    return len(blocks)


def main():
    parser = argparse.ArgumentParser(description="Export SRT to plain text")
    parser.add_argument("--srt", required=True, help="Input SRT file")
    parser.add_argument("--output", required=True, help="Output text file")
    parser.add_argument("--meta", help="Talk metadata YAML file")
    parser.add_argument(
        "--double-spacing",
        action="store_true",
        help="Use double line breaks between paragraphs (for transcript_uk.txt)",
    )
    args = parser.parse_args()

    count = export(args.srt, args.output, args.meta, double_spacing=args.double_spacing)
    print(f"Exported {count} blocks to {args.output}")


if __name__ == "__main__":
    main()
