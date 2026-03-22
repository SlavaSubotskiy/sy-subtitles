"""Deterministic orchestrator for building Ukrainian subtitle mappings.

Two modes:
  prepare  — split text, find boundaries, write chunk prompt files
  assemble — collect chunk results, build mapping, run build_srt

Usage (local):
    python -m tools.build_map prepare --talk-dir TALK --video-slug VIDEO
    python -m tools.build_map assemble --talk-dir TALK --video-slug VIDEO

In CI, `prepare` runs first, then matrix jobs process chunks via claude-code-action,
then `assemble` collects results.
"""

import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

from .align_uk import load_transcript
from .build_srt import build_srt as run_build_srt
from .generate_map import split_sentences, split_text_to_lines
from .srt_utils import load_whisper_json, ms_to_time

# --- Configuration ---
CHUNK_TARGET = 50
CHUNK_MAX = 80
CHUNK_MAX_PARAS = 15


# ---------------------------------------------------------------------------
# Step 1: Split UK text into subtitle blocks
# ---------------------------------------------------------------------------


def prepare_uk_blocks(uk_paragraphs):
    """Split UK paragraphs into subtitle blocks (≤84 CPL)."""
    blocks = []
    for para_idx, para in enumerate(uk_paragraphs):
        for sent in split_sentences(para):
            for line in split_text_to_lines(sent):
                blocks.append({"id": len(blocks) + 1, "text": line, "para_idx": para_idx})
    return blocks


# ---------------------------------------------------------------------------
# Step 2: Paragraph time boundaries (EN transcript ↔ whisper)
# ---------------------------------------------------------------------------


def _normalize(word):
    return re.sub(r"[^\w]", "", word.lower())


def find_paragraph_boundaries(en_paragraphs, whisper_segments):
    """Find whisper time boundaries for each EN paragraph via SequenceMatcher."""
    en_words = []
    for p_idx, para in enumerate(en_paragraphs):
        for word in para.split():
            nw = _normalize(word)
            if nw:
                en_words.append((nw, p_idx))

    w_words = []
    for seg in whisper_segments:
        for w in seg.get("words", []):
            nw = _normalize(w.get("word", ""))
            if nw:
                w_words.append((nw, w))

    if not en_words or not w_words:
        return [(0, 0)] * len(en_paragraphs)

    matcher = SequenceMatcher(None, [w[0] for w in en_words], [w[0] for w in w_words], autojunk=False)

    para_times = {}
    for op, i1, i2, j1, _j2 in matcher.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                _, p_idx = en_words[i1 + k]
                _, w_obj = w_words[j1 + k]
                s = int(w_obj["start"] * 1000)
                e = int(w_obj["end"] * 1000)
                if p_idx not in para_times:
                    para_times[p_idx] = (s, e)
                else:
                    old_s, old_e = para_times[p_idx]
                    para_times[p_idx] = (min(old_s, s), max(old_e, e))

    return [para_times.get(i, (0, 0)) for i in range(len(en_paragraphs))]


# ---------------------------------------------------------------------------
# Chunking by paragraph boundaries
# ---------------------------------------------------------------------------


def make_chunks(uk_blocks, para_boundaries):
    """Group blocks into chunks aligned to paragraph boundaries."""
    para_blocks = {}
    for b in uk_blocks:
        para_blocks.setdefault(b["para_idx"], []).append(b)

    para_indices = sorted(para_blocks.keys())
    chunks = []
    current_paras = []
    current_size = 0

    for p_idx in para_indices:
        p_size = len(para_blocks.get(p_idx, []))
        if (current_size + p_size > CHUNK_MAX or len(current_paras) >= CHUNK_MAX_PARAS) and current_paras:
            chunks.append(current_paras)
            current_paras = [p_idx]
            current_size = p_size
        elif current_size + p_size >= CHUNK_TARGET or len(current_paras) + 1 >= CHUNK_MAX_PARAS:
            current_paras.append(p_idx)
            chunks.append(current_paras)
            current_paras = []
            current_size = 0
        else:
            current_paras.append(p_idx)
            current_size += p_size

    if current_paras:
        chunks.append(current_paras)

    result = []
    for i, para_idxs in enumerate(chunks):
        blocks = []
        for p_idx in para_idxs:
            blocks.extend(para_blocks.get(p_idx, []))

        times = [para_boundaries[p] for p in para_idxs if p < len(para_boundaries)]
        valid = [(s, e) for s, e in times if s > 0 or e > 0]
        time_start = min(s for s, _ in valid) if valid else 0
        time_end = max(e for _, e in valid) if valid else 0

        result.append(
            {
                "idx": i,
                "para_indices": para_idxs,
                "blocks": blocks,
                "time_start_ms": time_start,
                "time_end_ms": time_end,
            }
        )
    return result


# ---------------------------------------------------------------------------
# Chunk prompt generation
# ---------------------------------------------------------------------------


def format_whisper_for_chunk(whisper_segments, start_ms, end_ms):
    """Format whisper data for a chunk's time range."""
    margin = 5000
    lines = []
    for seg in whisper_segments:
        seg_s = int(seg["start"] * 1000)
        seg_e = int(seg["end"] * 1000)
        if seg_e < start_ms - margin or seg_s > end_ms + margin:
            continue
        words = []
        for w in seg.get("words", []):
            ws = int(w["start"] * 1000)
            we = int(w["end"] * 1000)
            words.append(f"{w.get('word', '').strip()} {ms_to_time(ws)}->{ms_to_time(we)}")
        lines.append(f"[{ms_to_time(seg_s)}->{ms_to_time(seg_e)}] {seg['text'].strip()}")
        lines.append(f"  Words: {' | '.join(words)}")
    return "\n".join(lines)


def format_en_srt_for_chunk(en_srt_blocks, start_ms, end_ms):
    """Format EN SRT blocks for a chunk's time range."""
    margin = 5000
    lines = []
    for b in en_srt_blocks:
        if b["end_ms"] < start_ms - margin or b["start_ms"] > end_ms + margin:
            continue
        lines.append(f"EN#{b['idx']} [{ms_to_time(b['start_ms'])} -> {ms_to_time(b['end_ms'])}]: {b['text']}")
    return "\n".join(lines)


def build_chunk_prompt(uk_blocks, en_text, timing_text, time_start_ms, time_end_ms, timing_source="whisper"):
    """Build the full prompt for one chunk."""
    blocks_text = "\n".join(f"#{b['id']}: {b['text']}" for b in uk_blocks)

    if timing_source == "en-srt":
        return f"""Determine start and end timecodes for each Ukrainian subtitle block.

You have 3 sources:
1. UKRAINIAN BLOCKS — subtitle text needing timecodes
2. ENGLISH TRANSCRIPT — accurate English text (meaning reference)
3. ENGLISH SUBTITLES — EN SRT blocks with timecodes (timing source)

IMPORTANT TIME BOUNDARIES:
- This chunk covers audio from {ms_to_time(time_start_ms)} to {ms_to_time(time_end_ms)}
- Block #{uk_blocks[0]["id"]} must start at or after {ms_to_time(time_start_ms)}
- Block #{uk_blocks[-1]["id"]} must end at or before {ms_to_time(time_end_ms)}
- All timecodes must be within this range and sequential

Match Ukrainian blocks to English meaning, then find the corresponding
EN SRT block(s) and use their timecodes. If a Ukrainian block maps to
multiple EN SRT blocks, use the start of the first and end of the last.

ENGLISH TRANSCRIPT:
{en_text}

ENGLISH SUBTITLES (timing source):
{timing_text}

UKRAINIAN BLOCKS:
{blocks_text}

Output ONLY lines in this exact format, one per block:
#<number> | <start HH:MM:SS,mmm> | <end HH:MM:SS,mmm>

Blocks must be sequential and non-overlapping."""

    return f"""Determine start and end timecodes for each Ukrainian subtitle block.

You have 3 sources:
1. UKRAINIAN BLOCKS — subtitle text needing timecodes
2. ENGLISH TRANSCRIPT — accurate English text (meaning reference)
3. WHISPER DATA — English words with timestamps from audio (timing source)

IMPORTANT TIME BOUNDARIES:
- This chunk covers audio from {ms_to_time(time_start_ms)} to {ms_to_time(time_end_ms)}
- Block #{uk_blocks[0]["id"]} must start at or after {ms_to_time(time_start_ms)}
- Block #{uk_blocks[-1]["id"]} must end at or before {ms_to_time(time_end_ms)}
- All timecodes must be within this range and sequential

Match Ukrainian blocks to English meaning, then find corresponding whisper
word timestamps. Use the whisper word START time for block start, and the
whisper word END time for block end.

ENGLISH TRANSCRIPT:
{en_text}

WHISPER DATA:
{timing_text}

UKRAINIAN BLOCKS:
{blocks_text}

Output ONLY lines in this exact format, one per block:
#<number> | <start HH:MM:SS,mmm> | <end HH:MM:SS,mmm>

Blocks must be sequential and non-overlapping."""


# ---------------------------------------------------------------------------
# prepare command
# ---------------------------------------------------------------------------


def cmd_prepare(args):
    """Split text, find boundaries, write chunk files."""
    talk = Path(args.talk_dir)
    video = talk / args.video_slug
    work = video / "work"
    work.mkdir(parents=True, exist_ok=True)
    timing_source = getattr(args, "timing_source", "whisper")

    # Load
    print(f"Loading inputs (timing: {timing_source})...", file=sys.stderr)
    uk_paras = load_transcript(str(talk / "transcript_uk.txt"))
    en_paras = load_transcript(str(talk / "transcript_en.txt"))
    whisper_segs = load_whisper_json(str(video / "source" / "whisper.json"))

    en_srt_blocks = None
    if timing_source == "en-srt":
        from .srt_utils import parse_srt

        en_srt_blocks = parse_srt(str(video / "source" / "en.srt"))
        print(f"  EN SRT: {len(en_srt_blocks)} blocks", file=sys.stderr)

    print(f"  UK: {len(uk_paras)} paragraphs", file=sys.stderr)
    print(f"  EN: {len(en_paras)} paragraphs", file=sys.stderr)
    print(f"  Whisper: {len(whisper_segs)} segments", file=sys.stderr)

    # Step 1: Split
    print("Splitting UK text...", file=sys.stderr)
    uk_blocks = prepare_uk_blocks(uk_paras)
    print(f"  {len(uk_blocks)} blocks (all <= 84 CPL)", file=sys.stderr)

    # Save blocks for assemble step
    blocks_file = work / "uk_blocks.json"
    with open(blocks_file, "w", encoding="utf-8") as f:
        json.dump(uk_blocks, f, ensure_ascii=False, indent=2)

    # Step 2: Paragraph boundaries
    print("Finding paragraph boundaries...", file=sys.stderr)
    if timing_source == "en-srt" and en_srt_blocks:
        # Use SequenceMatcher to align EN transcript to EN SRT blocks
        en_words_seq = []
        for p_idx, para in enumerate(en_paras):
            for word in para.split():
                nw = _normalize(word)
                if nw:
                    en_words_seq.append((nw, p_idx))

        srt_words_seq = []
        for block in en_srt_blocks:
            for word in block["text"].split():
                nw = _normalize(word)
                if nw:
                    srt_words_seq.append((nw, block["idx"]))

        if en_words_seq and srt_words_seq:
            matcher = SequenceMatcher(
                None,
                [w[0] for w in en_words_seq],
                [w[0] for w in srt_words_seq],
                autojunk=False,
            )
            srt_lookup = {b["idx"]: b for b in en_srt_blocks}
            para_block_ids = {}  # para_idx -> set of block_idx
            for op, i1, i2, j1, _j2 in matcher.get_opcodes():
                if op == "equal":
                    for k in range(i2 - i1):
                        _, p_idx = en_words_seq[i1 + k]
                        _, b_idx = srt_words_seq[j1 + k]
                        para_block_ids.setdefault(p_idx, set()).add(b_idx)

            para_bounds = []
            for p_idx in range(len(en_paras)):
                b_ids = para_block_ids.get(p_idx, set())
                if b_ids:
                    blocks_in_para = [srt_lookup[bid] for bid in sorted(b_ids) if bid in srt_lookup]
                    if blocks_in_para:
                        para_bounds.append((blocks_in_para[0]["start_ms"], blocks_in_para[-1]["end_ms"]))
                    else:
                        para_bounds.append((0, 0))
                else:
                    para_bounds.append((0, 0))
        else:
            para_bounds = [(0, 0)] * len(en_paras)
    else:
        para_bounds = find_paragraph_boundaries(en_paras, whisper_segs)
    covered = sum(1 for s, e in para_bounds if s > 0 or e > 0)
    print(f"  {covered}/{len(en_paras)} paragraphs mapped", file=sys.stderr)

    # Chunking
    chunks = make_chunks(uk_blocks, para_bounds)
    print(f"  {len(chunks)} chunks", file=sys.stderr)

    # Write chunk prompt files
    matrix_items = []
    for chunk in chunks:
        idx = chunk["idx"]
        blocks = chunk["blocks"]
        para_idxs = chunk["para_indices"]

        en_text = "\n\n".join(f"[P{p + 1}] {en_paras[p]}" for p in para_idxs if p < len(en_paras))
        chunk_ts = timing_source
        if timing_source == "en-srt" and en_srt_blocks:
            no_coverage = chunk["time_start_ms"] == 0 and chunk["time_end_ms"] == 0
            if not no_coverage:
                timing_text = format_en_srt_for_chunk(en_srt_blocks, chunk["time_start_ms"], chunk["time_end_ms"])
            if no_coverage:
                # No EN SRT coverage — fall back to whisper for this chunk
                # Find nearest covered paragraphs before/after
                prev_end = 0
                next_start = int(whisper_segs[-1]["end"] * 1000) if whisper_segs else 0
                for p in range(min(chunk["para_indices"]) - 1, -1, -1):
                    if p < len(para_bounds) and para_bounds[p][1] > 0:
                        prev_end = para_bounds[p][1]
                        break
                for p in range(max(chunk["para_indices"]) + 1, len(para_bounds)):
                    if para_bounds[p][0] > 0:
                        next_start = para_bounds[p][0]
                        break
                chunk["time_start_ms"] = prev_end
                chunk["time_end_ms"] = next_start
                timing_text = format_whisper_for_chunk(whisper_segs, prev_end, next_start)
                chunk_ts = "whisper"
                print(
                    f"      No EN SRT coverage — whisper fallback {ms_to_time(prev_end)}..{ms_to_time(next_start)}",
                    file=sys.stderr,
                )
        else:
            timing_text = format_whisper_for_chunk(whisper_segs, chunk["time_start_ms"], chunk["time_end_ms"])
        prompt = build_chunk_prompt(
            blocks, en_text, timing_text, chunk["time_start_ms"], chunk["time_end_ms"], chunk_ts
        )

        prompt_file = work / f"chunk_{idx}.txt"
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(prompt)

        print(
            f"    Chunk {idx}: P{para_idxs[0] + 1}..P{para_idxs[-1] + 1} "
            f"({len(blocks)} blocks, {ms_to_time(chunk['time_start_ms'])}..{ms_to_time(chunk['time_end_ms'])}) "
            f"-> {prompt_file.name} ({len(prompt)} chars)",
            file=sys.stderr,
        )

        matrix_items.append({"ci": idx})

    # Output matrix JSON to stdout (only line on stdout)
    matrix = {"include": matrix_items}
    print(json.dumps(matrix))

    # Also save metadata
    meta = {
        "talk_dir": args.talk_dir,
        "video_slug": args.video_slug,
        "n_chunks": len(chunks),
        "n_blocks": len(uk_blocks),
    }
    with open(work / "build_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\nReady: {len(chunks)} chunks in {work}/", file=sys.stderr)


# ---------------------------------------------------------------------------
# assemble command
# ---------------------------------------------------------------------------


def cmd_assemble(args):
    """Collect chunk results, build mapping, run build_srt."""
    talk = Path(args.talk_dir)
    video = talk / args.video_slug
    work = video / "work"

    # Load blocks
    with open(work / "uk_blocks.json", encoding="utf-8") as f:
        uk_blocks = json.load(f)

    with open(work / "build_meta.json") as f:
        meta = json.load(f)

    n_chunks = meta["n_chunks"]
    print(f"Assembling {n_chunks} chunks, {len(uk_blocks)} blocks...", file=sys.stderr)

    # Parse all chunk results
    tc_re = re.compile(r"#(\d+)\s*\|\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\|\s*(\d{2}:\d{2}:\d{2},\d{3})")
    all_timecodes = {}
    errors = []

    for idx in range(n_chunks):
        result_file = work / f"chunk_{idx}_result.txt"
        if not result_file.exists():
            errors.append(f"Chunk {idx}: result file missing")
            continue

        text = result_file.read_text(encoding="utf-8")
        chunk_tc = {}
        for line in text.split("\n"):
            m = tc_re.search(line)
            if m:
                chunk_tc[int(m.group(1))] = (m.group(2), m.group(3))

        if not chunk_tc:
            errors.append(f"Chunk {idx}: no timecodes found in result")
            continue

        all_timecodes.update(chunk_tc)
        print(f"  Chunk {idx}: {len(chunk_tc)} timecodes", file=sys.stderr)

    # Check completeness
    expected = {b["id"] for b in uk_blocks}
    got = set(all_timecodes.keys())
    missing = sorted(expected - got)
    if missing:
        errors.append(f"{len(missing)} blocks missing timecodes: {missing[:20]}{'...' if len(missing) > 20 else ''}")

    if errors:
        for e in errors:
            print(f"  ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"  Total: {len(all_timecodes)}/{len(uk_blocks)} blocks", file=sys.stderr)

    # Check completeness
    expected = {b["id"] for b in uk_blocks}
    got = set(all_timecodes.keys())
    missing = expected - got
    if missing:
        print(f"  WARNING: {len(missing)} blocks without timecodes", file=sys.stderr)

    # Build mapping
    output_map = str(work / "uk.map")
    map_lines = []
    for block in uk_blocks:
        bid = block["id"]
        if bid in all_timecodes:
            start_tc, end_tc = all_timecodes[bid]
            map_lines.append(f"{bid} | {start_tc} | {end_tc} | {block['text']}")

    with open(output_map, "w", encoding="utf-8") as f:
        f.write("\n".join(map_lines) + "\n")
    print(f"Mapping: {output_map} ({len(map_lines)} blocks)", file=sys.stderr)

    # Build SRT
    output_srt = str(video / "final" / "uk.srt")
    report = str(video / "final" / "build_report.txt")
    Path(output_srt).parent.mkdir(parents=True, exist_ok=True)

    print("Building SRT...", file=sys.stderr)
    run_build_srt(output_map, output_srt, report)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    p = argparse.ArgumentParser(description="Build Ukrainian subtitle mapping")
    sub = p.add_subparsers(dest="command", required=True)

    prep = sub.add_parser("prepare", help="Split text and write chunk files")
    prep.add_argument("--talk-dir", required=True)
    prep.add_argument("--video-slug", required=True)
    prep.add_argument(
        "--timing-source",
        choices=["whisper", "en-srt"],
        default="whisper",
        help="Timing source: whisper (default) or en-srt (for non-English talks)",
    )

    asm = sub.add_parser("assemble", help="Collect chunk results and build SRT")
    asm.add_argument("--talk-dir", required=True)
    asm.add_argument("--video-slug", required=True)

    args = p.parse_args()

    if args.command == "prepare":
        cmd_prepare(args)
    elif args.command == "assemble":
        cmd_assemble(args)


if __name__ == "__main__":
    main()
