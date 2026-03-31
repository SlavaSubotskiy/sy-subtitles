"""Sync transcript_uk.txt text edits into existing uk.srt.

Only swaps text in SRT blocks where paragraph text changed.
If block count changes — fails (need full agent rebuild).

Usage:
    python -m tools.sync_transcript_to_srt \
        --talk-dir talks/TALK --video-slug VIDEO \
        --old-transcript OLD --new-transcript NEW
"""

import argparse
import sys
from pathlib import Path

from .align_uk import load_transcript
from .generate_map import split_sentences, split_text_to_lines
from .srt_utils import parse_srt, write_srt


def prepare_blocks(paragraphs: list) -> list:
    """Split paragraphs into subtitle-sized blocks (<=84 CPL)."""
    blocks = []
    for para_idx, para in enumerate(paragraphs):
        for sent in split_sentences(para):
            for line in split_text_to_lines(sent):
                blocks.append({"text": line, "para_idx": para_idx})
    return blocks


def find_paragraph_blocks(srt_blocks: list, para_blocks: list) -> list | None:
    """Find SRT block indices matching paragraph blocks by sequential text."""
    if not para_blocks or not srt_blocks:
        return None
    target = [b["text"] for b in para_blocks]
    for start in range(len(srt_blocks) - len(target) + 1):
        if all(srt_blocks[start + j]["text"] == target[j] for j in range(len(target))):
            return list(range(start, start + len(target)))
    return None


def sync_transcript(talk_dir: str, video_slug: str, old_transcript: str, new_transcript: str) -> dict:
    """Swap changed paragraph text in SRT. Fail if block count changes."""
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
        old_blocks = prepare_blocks([old_paras[p_idx]])
        new_blocks = prepare_blocks([new_paras[p_idx]])

        if len(old_blocks) != len(new_blocks):
            return {
                "error": f"P{p_idx + 1}: block count changed {len(old_blocks)} → {len(new_blocks)} (need full rebuild)"
            }

        srt_indices = find_paragraph_blocks(srt_blocks, old_blocks)
        if srt_indices is None:
            return {"error": f"P{p_idx + 1}: cannot find matching blocks in SRT"}

        for j, srt_idx in enumerate(srt_indices):
            srt_blocks[srt_idx]["text"] = new_blocks[j]["text"]
        total_updated += len(old_blocks)
        print(f"  P{p_idx + 1}: swapped {len(old_blocks)} blocks", file=sys.stderr)

    write_srt(srt_blocks, str(srt_path))
    print(f"Updated: {srt_path} ({total_updated} blocks)", file=sys.stderr)
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
