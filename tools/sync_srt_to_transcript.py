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


def _delete_from_transcript(text: str, cursor: int, old_t: str) -> dict:
    """Remove the first occurrence of `old_t` from `text` at/after `cursor`.

    Trims one adjacent space to avoid double-spaces. Returns a dict with
    `action` ("removed" or "skipped"), plus `text` and `cursor` when removed.
    Skipped means the text wasn't found — caller decides how to handle it.
    """
    pos = _find_in_transcript(text, old_t, cursor)
    if pos == -1:
        return {"action": "skipped"}
    end = pos + len(old_t)
    if pos > 0 and text[pos - 1] == " ":
        pos -= 1
    elif end < len(text) and text[end] == " ":
        end += 1
    return {"action": "removed", "text": text[:pos] + text[end:], "cursor": pos}


def _match_blocks_by_similarity(old_slice: list[str], new_slice: list[str]) -> list[int | None]:
    """Pair each old block with the most similar new block (ratio > 0.5).

    Returns a list parallel to `old_slice`; each entry is either the index
    in `new_slice` of the matched block, or None if the old block should be
    treated as a deletion. Each new block is matched at most once.
    """
    matches: list[int | None] = []
    available = list(range(len(new_slice)))
    for old_text in old_slice:
        best_idx = None
        best_ratio = 0.0
        for ni in available:
            ratio = difflib.SequenceMatcher(None, old_text, new_slice[ni]).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_idx = ni
        if best_idx is not None and best_ratio > 0.5:
            matches.append(best_idx)
            available.remove(best_idx)
        else:
            matches.append(None)
    return matches


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

    drifted = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            # Walk the cursor through these unchanged blocks so subsequent
            # find()s land in the right region of the transcript. The walk
            # is best-effort: SRTs in older talks have legitimate drift from
            # the transcript (manual edits, capitalization changes, etc.).
            # If a block isn't found we leave the cursor where it was —
            # ordering may then be approximate, but for delete-only PRs the
            # cursor doesn't matter and the workflow still does the right
            # thing.
            for k in range(i1, i2):
                pos = _find_in_transcript(text, old_texts[k], cursor)
                if pos == -1:
                    drifted += 1
                    continue
                cursor = pos + len(old_texts[k])

        elif tag == "replace":
            # Pair old blocks to new blocks by similarity ratio. Equal-count
            # replaces degenerate to 1:1; unequal-count replaces (edit + delete
            # bundled together by difflib) match what they can and treat any
            # unmatched old block as a deletion. Any unmatched *new* block is
            # a real insertion and errors out.
            old_slice = old_texts[i1:i2]
            new_slice = new_texts[j1:j2]
            matches = (
                list(range(i2 - i1)) if (i2 - i1) == (j2 - j1) else _match_blocks_by_similarity(old_slice, new_slice)
            )
            matched_new_indices = {m for m in matches if m is not None}
            unmatched_new = [ni for ni in range(len(new_slice)) if ni not in matched_new_indices]
            if unmatched_new:
                return {
                    "error": (
                        f"Block group replaced ({i2 - i1} → {j2 - j1}) with "
                        f"{len(unmatched_new)} unmatched new block(s) — likely an "
                        f"insertion. Run the full pipeline."
                    )
                }

            for local_idx, match_idx in enumerate(matches):
                old_t = old_slice[local_idx]
                src_block = old_blocks[i1 + local_idx]
                if match_idx is None:
                    # Treat as deletion
                    op = _delete_from_transcript(text, cursor, old_t)
                    if op["action"] == "skipped":
                        print(
                            f"  Block {src_block['idx']}: «{old_t[:60]}» not in transcript — skipping (placeholder?)",
                            file=sys.stderr,
                        )
                        skipped += 1
                    else:
                        text = op["text"]
                        cursor = op["cursor"]
                        removed += 1
                        print(
                            f"  Block {src_block['idx']}: removed «{old_t[:60]}»",
                            file=sys.stderr,
                        )
                    continue
                new_t = new_slice[match_idx]
                pos = _find_in_transcript(text, old_t, cursor)
                if pos == -1:
                    return {
                        "error": (
                            f"Block {src_block['idx']}: cannot find "
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
                    f"  Block {src_block['idx']}: «{old_t[:60]}» → «{new_t[:60]}»",
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
                op = _delete_from_transcript(text, cursor, old_t)
                if op["action"] == "skipped":
                    print(
                        f"  Block {old_blocks[k]['idx']}: «{old_t[:60]}» not in transcript — skipping (placeholder?)",
                        file=sys.stderr,
                    )
                    skipped += 1
                    continue
                text = op["text"]
                cursor = op["cursor"]
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

    if changed or removed:
        with open(transcript, "w", encoding="utf-8") as f:
            f.write(text)
        print(
            f"Updated transcript: {transcript} (changed: {changed}, removed: {removed}, skipped: {skipped})",
            file=sys.stderr,
        )
    if drifted:
        print(
            f"Note: {drifted} unchanged block(s) not found in transcript verbatim — "
            f"likely benign drift (capitalization, punctuation). Cursor walk continued best-effort.",
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
