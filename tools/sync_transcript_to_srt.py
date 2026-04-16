"""Sync transcript_uk.txt text edits into existing uk.srt.

Applies text changes from a transcript diff directly to SRT blocks
via difflib fragment matching.  This approach works regardless of
whether the SRT block structure matches prepare_blocks output (e.g.
whisper-built SRTs that combine sentences differently).

When a replacement pushes a block over MAX_CPL, returns an error —
the caller should fall back to the full pipeline, which rebuilds
timing from whisper.

Usage:
    python -m tools.sync_transcript_to_srt \
        --talk-dir talks/TALK --video-slug VIDEO \
        --old-transcript OLD --new-transcript NEW
"""

import argparse
import sys
from pathlib import Path

from .srt_utils import parse_srt, write_srt
from .text_segmentation import MAX_CPL, build_blocks_from_paragraphs, load_transcript


def prepare_blocks(paragraphs: list) -> list:
    """Split paragraphs into subtitle-sized blocks (<=84 CPL).

    Thin wrapper around text_segmentation.build_blocks_from_paragraphs — the
    canonical implementation shared with build_map.prepare_uk_blocks.
    """
    return build_blocks_from_paragraphs(paragraphs)


def find_paragraph_blocks(srt_blocks: list, para_blocks: list) -> list | None:
    """Find SRT block indices matching paragraph blocks by sequential text."""
    if not para_blocks or not srt_blocks:
        return None
    target = [b["text"] for b in para_blocks]
    for start in range(len(srt_blocks) - len(target) + 1):
        if all(srt_blocks[start + j]["text"] == target[j] for j in range(len(target))):
            return list(range(start, start + len(target)))
    return None


def _find_diff(old_para: str, new_para: str) -> tuple[str, str]:
    """Find the changed region between old and new paragraph text.

    Returns (old_fragment, new_fragment) — the minimal differing middle
    with enough surrounding context for unique matching in SRT blocks.
    """
    # Common prefix
    prefix_len = 0
    min_len = min(len(old_para), len(new_para))
    while prefix_len < min_len and old_para[prefix_len] == new_para[prefix_len]:
        prefix_len += 1

    # Common suffix (can't overlap prefix)
    suffix_len = 0
    max_suffix = min_len - prefix_len
    while suffix_len < max_suffix and old_para[-(suffix_len + 1)] == new_para[-(suffix_len + 1)]:
        suffix_len += 1

    old_end = len(old_para) - suffix_len if suffix_len else len(old_para)
    new_end = len(new_para) - suffix_len if suffix_len else len(new_para)
    old_mid = old_para[prefix_len:old_end]
    new_mid = new_para[prefix_len:new_end]

    # If the diff region is too short, include surrounding context
    # so the fragment is findable and unique in SRT blocks
    while len(old_mid) < 3 and (prefix_len > 0 or suffix_len > 0):
        if prefix_len > 0:
            prefix_len -= 1
        if suffix_len > 0:
            suffix_len -= 1
            old_end = len(old_para) - suffix_len if suffix_len else len(old_para)
            new_end = len(new_para) - suffix_len if suffix_len else len(new_para)
        old_mid = old_para[prefix_len:old_end]
        new_mid = new_para[prefix_len:new_end]

    return old_mid, new_mid


def _apply_diff(old_para: str, new_para: str, srt_blocks: list, p_idx: int) -> dict | None:
    """Apply text diff from old_para → new_para to SRT blocks.

    Finds the changed region (prefix/suffix trimming), then searches
    SRT blocks for the old fragment and replaces it in-place.

    Returns an error dict on failure, or None on success.
    """
    old_frag, new_frag = _find_diff(old_para, new_para)

    if not old_frag:
        return {"error": (f"P{p_idx + 1}: cannot determine changed text — run the full subtitle pipeline to rebuild")}

    found = False
    for block in srt_blocks:
        if old_frag in block["text"]:
            block["text"] = block["text"].replace(old_frag, new_frag, 1)
            found = True
            print(
                f"  P{p_idx + 1}: «{old_frag[:60]}» → «{new_frag[:60]}»",
                file=sys.stderr,
            )
            break

    if not found:
        return {"error": (f"P{p_idx + 1}: cannot find «{old_frag[:60]}» in SRT blocks")}

    # CPL check on all blocks after replacement
    for block in srt_blocks:
        if len(block["text"]) > MAX_CPL:
            return {
                "error": (
                    f"P{p_idx + 1}: block exceeds {MAX_CPL} CPL after edit — run the full subtitle pipeline to re-split"
                )
            }

    return None


def sync_transcript(talk_dir: str, video_slug: str, old_transcript: str, new_transcript: str) -> dict:
    """Apply changed paragraph text to SRT via difflib fragment matching.

    For each changed paragraph, computes a character-level diff and applies
    the replacements directly to the SRT blocks that contain the old text.
    This works even when SRT block boundaries differ from what prepare_blocks
    would produce (e.g. whisper-built SRTs).
    """
    old_paras = load_transcript(old_transcript)
    new_paras = load_transcript(new_transcript)
    srt_path = Path(talk_dir) / video_slug / "final" / "uk.srt"

    if not srt_path.exists():
        return {"error": f"No SRT: {srt_path}"}

    if len(old_paras) != len(new_paras):
        return {"error": f"Paragraph count changed: {len(old_paras)} → {len(new_paras)} (need full rebuild)"}

    srt_blocks = parse_srt(str(srt_path))

    changed_paras = [i for i, (o, n) in enumerate(zip(old_paras, new_paras, strict=True)) if o != n]
    if not changed_paras:
        return {"changed": 0}

    print(f"Changed paragraphs: {len(changed_paras)}", file=sys.stderr)

    total_updated = 0
    for p_idx in changed_paras:
        err = _apply_diff(old_paras[p_idx], new_paras[p_idx], srt_blocks, p_idx)
        if err:
            return err
        total_updated += 1

    # Renumber
    for i, b in enumerate(srt_blocks):
        b["idx"] = i + 1

    write_srt(srt_blocks, str(srt_path))
    print(f"Updated: {srt_path} ({total_updated} paragraphs)", file=sys.stderr)
    return {"changed": len(changed_paras), "updated_blocks": total_updated}


def main():
    p = argparse.ArgumentParser(description="Sync transcript edits to subtitles")
    p.add_argument("--talk-dir", required=True)
    p.add_argument("--video-slug", required=True)
    p.add_argument("--old-transcript", required=True)
    p.add_argument("--new-transcript", required=True)
    args = p.parse_args()

    result = sync_transcript(args.talk_dir, args.video_slug, args.old_transcript, args.new_transcript)
    if result.get("error"):
        print(f"FAIL: {result['error']}", file=sys.stderr)
        sys.exit(1)
    if result["changed"] == 0:
        print("No changes", file=sys.stderr)


if __name__ == "__main__":
    main()
