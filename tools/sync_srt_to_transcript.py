"""Sync subtitle text edits back into transcript_uk.txt.

Mirror of sync_transcript_to_srt: takes the diff between an old and a
new SRT, then applies the per-block text changes to the transcript file
in-place. Block count must be unchanged (this is a text-edit propagator,
not a structural rebuild).

Usage:
    python -m tools.sync_srt_to_transcript \
        --old-srt OLD --new-srt NEW --transcript transcript_uk.txt
"""

import argparse
import sys

from .srt_utils import parse_srt


def sync_srt_to_transcript(old_srt: str, new_srt: str, transcript: str) -> dict:
    """Apply text edits between old_srt and new_srt to the transcript file.

    Returns a dict with `changed` (number of edited blocks) or `error`.
    """
    old_blocks = parse_srt(old_srt)
    new_blocks = parse_srt(new_srt)

    if len(old_blocks) != len(new_blocks):
        return {
            "error": (
                f"Block count changed: {len(old_blocks)} → {len(new_blocks)}. "
                "Text-only sync requires identical block count."
            )
        }

    with open(transcript, encoding="utf-8") as f:
        text = f.read()

    cursor = 0
    changed = 0
    for old_b, new_b in zip(old_blocks, new_blocks, strict=True):
        old_text = old_b["text"]
        new_text = new_b["text"]
        pos = text.find(old_text, cursor)
        if pos == -1:
            return {
                "error": (
                    f"Block {old_b['idx']}: cannot find «{old_text[:60]}…» in transcript "
                    f"(searching from offset {cursor}). Transcript may have drifted from SRT."
                )
            }
        if old_text == new_text:
            cursor = pos + len(old_text)
            continue
        text = text[:pos] + new_text + text[pos + len(old_text) :]
        cursor = pos + len(new_text)
        changed += 1
        print(f"  Block {old_b['idx']}: «{old_text[:60]}» → «{new_text[:60]}»", file=sys.stderr)

    if changed:
        with open(transcript, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Updated transcript: {transcript} ({changed} blocks)", file=sys.stderr)

    return {"changed": changed}


def main():
    p = argparse.ArgumentParser(description="Sync SRT text edits back to transcript")
    p.add_argument("--old-srt", required=True)
    p.add_argument("--new-srt", required=True)
    p.add_argument("--transcript", required=True)
    args = p.parse_args()

    result = sync_srt_to_transcript(args.old_srt, args.new_srt, args.transcript)
    if result.get("error"):
        print(f"FAIL: {result['error']}", file=sys.stderr)
        sys.exit(1)
    if result["changed"] == 0:
        print("No changes", file=sys.stderr)


if __name__ == "__main__":
    main()
