"""Resync a UK SRT from a primary video's timeline onto a secondary video's timeline.

Given:
  - Primary video's UK SRT (built against primary's timeline)
  - Primary video's EN SRT
  - Secondary video's EN SRT (typically a subset of primary's spoken content —
    e.g. only the English-speech portion of a puja that alternates with Marathi)

Produce:
  - Secondary video's UK SRT with UK text and secondary's timing.

Only UK blocks whose primary timestamps fall inside the aligned region are
emitted; everything outside (content not present in secondary) is dropped.

Usage:
    python -m tools.resync_srt \\
        --primary-uk primary/final/uk.srt \\
        --primary-en primary/source/en.srt \\
        --secondary-en secondary/source/en.srt \\
        --output secondary/final/uk.srt
"""

from __future__ import annotations

import argparse
import re
import sys
from difflib import SequenceMatcher

from .build_srt import build_srt_from_blocks
from .srt_utils import parse_srt


def _normalize_word(word: str) -> str:
    return re.sub(r"[^\w]", "", word.lower())


def _blocks_to_words(blocks: list[dict]) -> list[tuple[str, int]]:
    """Flatten SRT blocks into (normalized_word, approx_time_ms) pairs.

    Each block's time is distributed linearly across its words — good enough
    for building an alignment anchor map between two EN SRTs.
    """
    out: list[tuple[str, int]] = []
    for b in blocks:
        words = b["text"].split()
        if not words:
            continue
        span = max(b["end_ms"] - b["start_ms"], 1)
        per_word = span / len(words)
        for i, w in enumerate(words):
            nw = _normalize_word(w)
            if nw:
                t = b["start_ms"] + int(i * per_word)
                out.append((nw, t))
    return out


def _build_anchor_map(primary_en: list[dict], secondary_en: list[dict]) -> list[tuple[int, int]]:
    """Return monotonic list of (primary_ms, secondary_ms) anchors from matched words."""
    p_words = _blocks_to_words(primary_en)
    s_words = _blocks_to_words(secondary_en)
    if not p_words or not s_words:
        return []

    matcher = SequenceMatcher(
        None,
        [w[0] for w in p_words],
        [w[0] for w in s_words],
        autojunk=False,
    )
    anchors: list[tuple[int, int]] = []
    for op, i1, i2, j1, _j2 in matcher.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                anchors.append((p_words[i1 + k][1], s_words[j1 + k][1]))
    # Ensure monotonic in primary time (anchors already come in primary order
    # from get_opcodes), but drop any out-of-order secondary anchors.
    cleaned: list[tuple[int, int]] = []
    last_s = -1
    for p, s in anchors:
        if s >= last_s:
            cleaned.append((p, s))
            last_s = s
    return cleaned


_EDGE_EXTRAPOLATION_MS = 2000


def _remap(primary_ms: int, anchors: list[tuple[int, int]]) -> int | None:
    """Interpolate primary_ms onto secondary timeline using anchors.

    Inside the anchor range: linear interpolation between neighbouring anchors.
    Just outside (up to _EDGE_EXTRAPOLATION_MS): extrapolate using the nearest
    anchor segment's gradient — SRT blocks commonly extend slightly past the
    last aligned word or start a bit before the first.

    Returns None when primary_ms is too far outside the covered range.
    """
    if not anchors:
        return None
    first_p, first_s = anchors[0]
    last_p, last_s = anchors[-1]

    if primary_ms < first_p:
        if first_p - primary_ms > _EDGE_EXTRAPOLATION_MS:
            return None
        if len(anchors) >= 2:
            next_p, next_s = anchors[1]
            span_p = next_p - first_p
            if span_p > 0:
                slope = (next_s - first_s) / span_p
                return max(0, int(first_s - slope * (first_p - primary_ms)))
        return max(0, first_s - (first_p - primary_ms))

    if primary_ms > last_p:
        if primary_ms - last_p > _EDGE_EXTRAPOLATION_MS:
            return None
        if len(anchors) >= 2:
            prev_p, prev_s = anchors[-2]
            span_p = last_p - prev_p
            if span_p > 0:
                slope = (last_s - prev_s) / span_p
                return int(last_s + slope * (primary_ms - last_p))
        return last_s + (primary_ms - last_p)

    lo_p, lo_s = first_p, first_s
    for p, s in anchors:
        if p >= primary_ms:
            if p == lo_p:
                return lo_s
            frac = (primary_ms - lo_p) / (p - lo_p)
            return int(lo_s + frac * (s - lo_s))
        lo_p, lo_s = p, s
    return last_s


def resync(primary_uk_path: str, primary_en_path: str, secondary_en_path: str, output_path: str) -> None:
    primary_uk = parse_srt(primary_uk_path)
    primary_en = parse_srt(primary_en_path)
    secondary_en = parse_srt(secondary_en_path)

    if not primary_uk:
        print(f"ERROR: primary uk.srt at {primary_uk_path} is empty", file=sys.stderr)
        sys.exit(1)

    anchors = _build_anchor_map(primary_en, secondary_en)
    if not anchors:
        print("ERROR: no text alignment found between primary and secondary EN SRTs", file=sys.stderr)
        sys.exit(1)

    covered_start, covered_end = anchors[0][0], anchors[-1][0]
    print(
        f"Alignment: {len(anchors)} word anchors, primary range {covered_start}ms — {covered_end}ms",
        file=sys.stderr,
    )

    output_blocks: list[dict] = []
    dropped_outside = 0
    dropped_unmapped = 0
    for b in primary_uk:
        # Fast-path drop for blocks wholly outside the aligned region (with
        # the same edge tolerance _remap uses). Blocks straddling an edge
        # still go through _remap, which extrapolates within the tolerance.
        if b["end_ms"] < covered_start - _EDGE_EXTRAPOLATION_MS or b["start_ms"] > covered_end + _EDGE_EXTRAPOLATION_MS:
            dropped_outside += 1
            continue
        new_start = _remap(b["start_ms"], anchors)
        new_end = _remap(b["end_ms"], anchors)
        if new_start is None or new_end is None:
            dropped_unmapped += 1
            continue
        if new_end <= new_start:
            new_end = new_start + 1
        output_blocks.append(
            {
                "idx": len(output_blocks) + 1,
                "start_ms": new_start,
                "end_ms": new_end,
                "text": b["text"],
            }
        )

    print(
        f"Resynced: {len(output_blocks)}/{len(primary_uk)} blocks "
        f"(dropped {dropped_outside} outside range, {dropped_unmapped} unmapped)",
        file=sys.stderr,
    )
    # Interpolation creates overlaps, tight gaps, and occasional high-CPS
    # blocks at anchor seams. Run the full build_srt timing pipeline
    # (gap enforcement, CPS balancing, duration, padding) to clean up.
    build_srt_from_blocks(output_blocks, output_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Resync UK SRT from primary to secondary timeline")
    parser.add_argument("--primary-uk", required=True, help="Primary video's built UK SRT")
    parser.add_argument("--primary-en", required=True, help="Primary video's EN SRT")
    parser.add_argument("--secondary-en", required=True, help="Secondary video's EN SRT")
    parser.add_argument("--output", required=True, help="Output path for secondary UK SRT")
    args = parser.parse_args()
    resync(args.primary_uk, args.primary_en, args.secondary_en, args.output)


if __name__ == "__main__":
    main()
