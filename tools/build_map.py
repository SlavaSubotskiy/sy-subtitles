"""Deterministic orchestrator for building Ukrainian subtitle mappings.

Commands:
  prepare        — split transcript into uk_blocks.json
  prepare-timing — write compact timing.json (whisper words or EN SRT blocks)
  assemble       — read timecodes.txt + uk_blocks.json → uk.map → build_srt

Usage (local):
    python -m tools.build_map prepare --talk-dir TALK --video-slug VIDEO
    python -m tools.build_map prepare-timing --talk-dir TALK --video-slug VIDEO
    python -m tools.build_map assemble --talk-dir TALK --video-slug VIDEO

In CI, `prepare` and `prepare-timing` run first, then a single Opus 4.7 agent
session produces timecodes.txt, then `assemble` builds the final SRT.
"""

import argparse
import json
import re
import sys
from pathlib import Path

from .build_srt import build_srt_from_blocks
from .srt_utils import load_whisper_json, time_to_ms
from .text_segmentation import build_blocks_from_paragraphs, load_transcript

# Regex for parsing timecodes output from the LLM
TC_RE = re.compile(r"#(\d+)\s*\|\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\|\s*(\d{2}:\d{2}:\d{2},\d{3})")


def _normalize(word):
    return re.sub(r"[^\w]", "", word.lower())


# ---------------------------------------------------------------------------
# prepare command — split UK text into subtitle blocks
# ---------------------------------------------------------------------------


def cmd_prepare(args):
    """Split UK transcript into subtitle blocks, save uk_blocks.json."""
    talk = Path(args.talk_dir)
    video = talk / args.video_slug
    work = video / "work"
    work.mkdir(parents=True, exist_ok=True)

    uk_paras = load_transcript(str(talk / "transcript_uk.txt"))
    uk_blocks = build_blocks_from_paragraphs(uk_paras)

    blocks_file = work / "uk_blocks.json"
    with open(blocks_file, "w", encoding="utf-8") as f:
        json.dump(uk_blocks, f, ensure_ascii=False, indent=2)

    print(f"  {len(uk_blocks)} blocks → {blocks_file}", file=sys.stderr)
    # Emit empty matrix (no chunks needed) — kept for workflow compatibility
    print("{}")


# ---------------------------------------------------------------------------
# prepare-timing command — build compact timing.json
# ---------------------------------------------------------------------------


def cmd_prepare_timing(args):
    """Write compact timing.json from whisper.json or en.srt."""
    talk = Path(args.talk_dir)
    video = talk / args.video_slug
    work = video / "work"
    work.mkdir(parents=True, exist_ok=True)
    timing_source = getattr(args, "timing_source", "whisper")

    if timing_source == "en-srt":
        from .srt_utils import parse_srt

        en_srt = parse_srt(str(video / "source" / "en.srt"))
        data = {
            "source": "en-srt",
            "blocks": [{"n": b["idx"], "s": b["start_ms"], "e": b["end_ms"], "t": b["text"]} for b in en_srt],
        }
        print(f"  EN SRT: {len(data['blocks'])} blocks", file=sys.stderr)
    else:
        segs = load_whisper_json(str(video / "source" / "whisper.json"))
        words = []
        for seg in segs:
            for w in seg.get("words", []):
                word_text = w.get("word", "").strip()
                if word_text:
                    words.append(
                        {
                            "w": word_text,
                            "s": int(w["start"] * 1000),
                            "e": int(w["end"] * 1000),
                        }
                    )
        data = {"source": "whisper", "words": words}
        print(f"  Whisper: {len(words)} words from {len(segs)} segments", file=sys.stderr)

    timing_file = work / "timing.json"
    with open(timing_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    size_kb = timing_file.stat().st_size // 1024
    print(f"  timing.json: {size_kb} KB → {timing_file}", file=sys.stderr)


# ---------------------------------------------------------------------------
# assemble command — timecodes.txt + uk_blocks.json → uk.srt (in-memory merge)
# ---------------------------------------------------------------------------


def cmd_assemble(args):
    """Merge LLM timecodes with UK blocks in memory, run build_srt."""
    talk = Path(args.talk_dir)
    video = talk / args.video_slug
    work = video / "work"

    with open(work / "uk_blocks.json", encoding="utf-8") as f:
        uk_blocks = json.load(f)

    timecodes_file = work / "timecodes.txt"
    if not timecodes_file.exists():
        print(f"ERROR: {timecodes_file} not found", file=sys.stderr)
        sys.exit(1)

    text = timecodes_file.read_text(encoding="utf-8")
    all_timecodes = {}
    for line in text.split("\n"):
        m = TC_RE.search(line)
        if m:
            all_timecodes[int(m.group(1))] = (m.group(2), m.group(3))

    expected = {b["id"] for b in uk_blocks}
    missing = sorted(expected - set(all_timecodes.keys()))
    if missing:
        print(
            f"ERROR: {len(missing)} blocks missing timecodes: {missing[:20]}{'...' if len(missing) > 20 else ''}",
            file=sys.stderr,
        )
        sys.exit(1)

    blocks = []
    for block in uk_blocks:
        bid = block["id"]
        start_tc, end_tc = all_timecodes[bid]
        start_ms = time_to_ms(start_tc)
        end_ms = time_to_ms(end_tc)
        if start_ms >= end_ms:
            print(f"ERROR: block #{bid} has start {start_tc} >= end {end_tc}", file=sys.stderr)
            sys.exit(1)
        blocks.append({"idx": bid, "start_ms": start_ms, "end_ms": end_ms, "text": block["text"]})

    print(f"  {len(blocks)}/{len(uk_blocks)} blocks merged", file=sys.stderr)

    output_srt = str(video / "final" / "uk.srt")
    report = str(video / "final" / "build_report.txt")
    Path(output_srt).parent.mkdir(parents=True, exist_ok=True)
    build_srt_from_blocks(blocks, output_srt, report)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    p = argparse.ArgumentParser(description="Build Ukrainian subtitle mapping")
    sub = p.add_subparsers(dest="command", required=True)

    prep = sub.add_parser("prepare", help="Split UK text into subtitle blocks")
    prep.add_argument("--talk-dir", required=True)
    prep.add_argument("--video-slug", required=True)
    prep.add_argument(
        "--timing-source",
        choices=["whisper", "en-srt"],
        default="whisper",
        help="(unused, kept for workflow compatibility)",
    )

    pt = sub.add_parser("prepare-timing", help="Write compact timing.json from whisper/en-srt")
    pt.add_argument("--talk-dir", required=True)
    pt.add_argument("--video-slug", required=True)
    pt.add_argument(
        "--timing-source",
        choices=["whisper", "en-srt"],
        default="whisper",
    )

    asm = sub.add_parser("assemble", help="Build uk.map from timecodes.txt + uk_blocks.json")
    asm.add_argument("--talk-dir", required=True)
    asm.add_argument("--video-slug", required=True)

    args = p.parse_args()
    if args.command == "prepare":
        cmd_prepare(args)
    elif args.command == "prepare-timing":
        cmd_prepare_timing(args)
    elif args.command == "assemble":
        cmd_assemble(args)


if __name__ == "__main__":
    main()
