"""Sync subtitle text edits back into transcript_uk.txt.

Mirror of sync_transcript_to_srt: takes the diff between an old and a
new SRT, then applies the changes to the transcript file in-place.

Supported edits:
  - text-only edits (block count unchanged)
  - block deletions (e.g. removing a placeholder block) — the deleted
    text is removed from the transcript if found, otherwise skipped
    silently (placeholders are often not in the transcript)

Unsupported (returns error):
  - block insertions — there's no signal where to insert text in the
    transcript; needs full pipeline rebuild
  - block-group replacements with different counts — too ambiguous
    for automated propagation; needs full pipeline rebuild

After processing the new SRT is rewritten via write_srt, which
normalizes block numbering — handy when the user deleted blocks but
forgot to renumber.

Usage:
    python -m tools.sync_srt_to_transcript \
        --old-srt OLD --new-srt NEW --transcript transcript_uk.txt
"""

import argparse
import difflib
import sys

from .srt_utils import parse_srt, write_srt


def _find_in_transcript(text: str, needle: str, cursor: int) -> int:
    """Return position of needle in text starting at cursor, or -1."""
    return text.find(needle, cursor)


def sync_srt_to_transcript(old_srt: str, new_srt: str, transcript: str) -> dict:
    """Apply text-level diff between old_srt and new_srt to the transcript file.

    Returns a dict with `changed` (number of edited blocks), `removed`
    (number of removed blocks), `skipped` (deletions of blocks not in
    transcript), or `error`.
    """
    old_blocks = parse_srt(old_srt)
    new_blocks = parse_srt(new_srt)

    with open(transcript, encoding="utf-8") as f:
        text = f.read()

    old_texts = [b["text"] for b in old_blocks]
    new_texts = [b["text"] for b in new_blocks]
    matcher = difflib.SequenceMatcher(a=old_texts, b=new_texts, autojunk=False)

    cursor = 0
    changed = 0
    removed = 0
    skipped = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            # Walk the cursor through these unchanged blocks so subsequent
            # find()s land in the right region of the transcript.
            for k in range(i1, i2):
                pos = _find_in_transcript(text, old_texts[k], cursor)
                if pos == -1:
                    return {
                        "error": (
                            f"Block {old_blocks[k]['idx']}: cannot find "
                            f"«{old_texts[k][:60]}» in transcript "
                            f"(searching from offset {cursor}). Transcript may have drifted from SRT."
                        )
                    }
                cursor = pos + len(old_texts[k])

        elif tag == "replace" and (i2 - i1) == (j2 - j1):
            # 1:1 text substitution
            for offset in range(i2 - i1):
                old_t = old_texts[i1 + offset]
                new_t = new_texts[j1 + offset]
                pos = _find_in_transcript(text, old_t, cursor)
                if pos == -1:
                    return {
                        "error": (
                            f"Block {old_blocks[i1 + offset]['idx']}: cannot find "
                            f"«{old_t[:60]}» in transcript (searching from offset {cursor})."
                        )
                    }
                if old_t == new_t:
                    cursor = pos + len(old_t)
                    continue
                text = text[:pos] + new_t + text[pos + len(old_t) :]
                cursor = pos + len(new_t)
                changed += 1
                print(
                    f"  Block {old_blocks[i1 + offset]['idx']}: «{old_t[:60]}» → «{new_t[:60]}»",
                    file=sys.stderr,
                )

        elif tag == "delete":
            # Blocks i1:i2 were removed from the SRT. Try to find each
            # removed block's text in the transcript and remove it. If a
            # block isn't in the transcript (placeholder, technical note),
            # skip silently — the SRT change stands but the transcript was
            # never the source of that text.
            for k in range(i1, i2):
                old_t = old_texts[k]
                pos = _find_in_transcript(text, old_t, cursor)
                if pos == -1:
                    print(
                        f"  Block {old_blocks[k]['idx']}: «{old_t[:60]}» not in transcript — skipping (placeholder?)",
                        file=sys.stderr,
                    )
                    skipped += 1
                    continue
                end = pos + len(old_t)
                # Trim a single adjacent space so we don't leave a double space
                if pos > 0 and text[pos - 1] == " ":
                    pos -= 1
                elif end < len(text) and text[end] == " ":
                    end += 1
                text = text[:pos] + text[end:]
                cursor = pos
                removed += 1
                print(
                    f"  Block {old_blocks[k]['idx']}: removed «{old_t[:60]}»",
                    file=sys.stderr,
                )

        elif tag == "insert":
            return {
                "error": (
                    f"Cannot propagate inserted blocks ({j2 - j1} new) — "
                    f"transcript has no signal where to put new text. Run the full pipeline."
                )
            }
        else:  # tag == 'replace' with unequal counts
            return {
                "error": (
                    f"Block group replaced ({i2 - i1} → {j2 - j1}) — "
                    f"too ambiguous for text-level propagation. Run the full pipeline."
                )
            }

    if changed or removed:
        with open(transcript, "w", encoding="utf-8") as f:
            f.write(text)
        print(
            f"Updated transcript: {transcript} (changed: {changed}, removed: {removed}, skipped: {skipped})",
            file=sys.stderr,
        )

    # Always normalize the new SRT's block numbering. The user may have
    # deleted blocks without renumbering; write_srt always emits sequential
    # indices starting at 1.
    write_srt(new_blocks, new_srt)

    return {"changed": changed, "removed": removed, "skipped": skipped}


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
    if result["changed"] == 0 and result.get("removed", 0) == 0:
        print("No changes", file=sys.stderr)


if __name__ == "__main__":
    main()
