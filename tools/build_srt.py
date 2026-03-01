"""Build SRT from agent mapping file.

Takes a pipe-separated mapping (block# | start | end | text) produced by the
builder agent and applies padding, gap enforcement, and duration enforcement
to produce a valid SRT file.

Usage:
    python -m tools.build_srt --mapping PATH --output PATH [--report PATH]
"""

import argparse
import sys

from .config import OptimizeConfig
from .srt_utils import ms_to_time, time_to_ms, write_srt


def parse_mapping(filepath):
    """Parse pipe-separated mapping into blocks.

    Format: block# | start_tc | end_tc | text
    Skips blank lines and # comments.

    Returns list of {idx, start_ms, end_ms, text}.
    """
    blocks = []
    with open(filepath, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            if len(parts) < 4:
                print(f"WARNING: line {line_no}: expected 4+ pipe-separated fields, got {len(parts)}: {line[:80]}")
                continue
            try:
                idx = int(parts[0].strip())
            except ValueError:
                print(f"WARNING: line {line_no}: invalid block number '{parts[0].strip()}'")
                continue
            try:
                start_ms = time_to_ms(parts[1].strip())
                end_ms = time_to_ms(parts[2].strip())
            except (ValueError, IndexError):
                print(f"WARNING: line {line_no}: invalid timecode in '{parts[1].strip()}' or '{parts[2].strip()}'")
                continue
            # Text may contain pipes (unlikely but safe)
            text = "|".join(parts[3:]).strip()

            if start_ms >= end_ms:
                print(
                    f"WARNING: line {line_no}: start >= end for block #{idx} ({parts[1].strip()} >= {parts[2].strip()})"
                )
                continue

            blocks.append(
                {
                    "idx": idx,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "text": text,
                }
            )

    # Validate sequential numbering
    for i, b in enumerate(blocks):
        expected = i + 1
        if b["idx"] != expected:
            print(f"WARNING: expected block #{expected}, got #{b['idx']}")

    return blocks


def apply_padding(blocks, config=None):
    """Extend block end times into silence for readability.

    For each block, extend end to: min(next_start - gap, end + 5000ms, max_duration).
    Last block: extend up to +2000ms.
    """
    if config is None:
        config = OptimizeConfig()

    max_pad_ms = 5000
    last_block_pad_ms = 2000
    result = []

    for i, b in enumerate(blocks):
        b = dict(b)  # copy
        original_end = b["end_ms"]
        # Cap so block doesn't exceed max duration
        max_end = b["start_ms"] + config.max_duration_ms

        if i < len(blocks) - 1:
            next_start = blocks[i + 1]["start_ms"]
            # Extend into silence: up to next block start minus gap
            padded_end = next_start - config.min_gap_ms
            # Cap at max padding
            padded_end = min(padded_end, original_end + max_pad_ms)
            # Cap at max duration
            padded_end = min(padded_end, max_end)
            # Never shrink below original end
            b["end_ms"] = max(padded_end, original_end)
        else:
            # Last block: modest extension, capped at max duration
            b["end_ms"] = min(original_end + last_block_pad_ms, max_end)

        result.append(b)

    return result


def enforce_gaps(blocks, config=None):
    """Ensure minimum gap between consecutive blocks.

    If gap < min_gap_ms: shrink previous block's end.
    Warns if overlap > 2000ms (likely mapping error).
    """
    if config is None:
        config = OptimizeConfig()

    warnings = []
    result = [dict(b) for b in blocks]  # deep copy

    for i in range(1, len(result)):
        gap = result[i]["start_ms"] - result[i - 1]["end_ms"]
        if gap < config.min_gap_ms:
            if gap < -2000:
                warnings.append(
                    f"  Large overlap: #{result[i - 1]['idx']}→#{result[i]['idx']} = {-gap}ms (possible mapping error)"
                )
            # Shrink previous block's end to create the gap
            result[i - 1]["end_ms"] = result[i]["start_ms"] - config.min_gap_ms
            # Ensure prev block doesn't become zero/negative duration
            if result[i - 1]["end_ms"] <= result[i - 1]["start_ms"]:
                # Can't fix by shrinking prev — move current start forward instead
                result[i - 1]["end_ms"] = result[i - 1]["start_ms"] + config.min_duration_ms
                result[i]["start_ms"] = result[i - 1]["end_ms"] + config.min_gap_ms
                warnings.append(
                    f"  Forced gap: #{result[i - 1]['idx']}→#{result[i]['idx']} "
                    f"(moved block #{result[i]['idx']} start forward)"
                )

    for w in warnings:
        print(w)

    return result


def enforce_duration(blocks, config=None):
    """Extend blocks shorter than min_duration if gap allows.

    Tries extending end first, then start (backwards). Reports unfixable issues.
    """
    if config is None:
        config = OptimizeConfig()

    warnings = []
    result = [dict(b) for b in blocks]

    for i, b in enumerate(result):
        duration = b["end_ms"] - b["start_ms"]
        if duration < config.min_duration_ms:
            needed = config.min_duration_ms - duration
            # Try extending end
            if i < len(result) - 1:
                available = result[i + 1]["start_ms"] - b["end_ms"] - config.min_gap_ms
                extend = min(needed, max(0, available))
                b["end_ms"] += extend
                needed -= extend
            else:
                # Last block — just extend
                b["end_ms"] = b["start_ms"] + config.min_duration_ms
                needed = 0

            # Try extending start (backwards) if still short
            if needed > 0 and i > 0:
                available = b["start_ms"] - result[i - 1]["end_ms"] - config.min_gap_ms
                extend = min(needed, max(0, available))
                b["start_ms"] -= extend
                needed -= extend
            elif needed > 0 and i == 0:
                # First block — extend start towards 0
                extend = min(needed, b["start_ms"])
                b["start_ms"] -= extend
                needed -= extend

            new_duration = b["end_ms"] - b["start_ms"]
            if new_duration < config.min_duration_ms:
                warnings.append(f"  Short block #{b['idx']}: {new_duration}ms < {config.min_duration_ms}ms (unfixable)")

    for w in warnings:
        print(w)

    return result


def _cps(block):
    """Calculate CPS for a block."""
    dur_s = (block["end_ms"] - block["start_ms"]) / 1000.0
    if dur_s <= 0:
        return 999
    return len(block["text"].replace("\n", "")) / dur_s


def balance_cps(blocks, config=None, threshold=None):
    """Balance CPS by shifting neighbors into nearby silence (gaps).

    For blocks with CPS > threshold: find gaps in the neighborhood,
    shift intermediate blocks wholesale (preserving their duration),
    and extend the high-CPS block into the opened space.

    Neighbors are NOT resized — only shifted into existing silence.
    """
    if config is None:
        config = OptimizeConfig()
    if threshold is None:
        threshold = config.hard_max_cps

    max_passes = 10
    max_cascade = 10  # search up to 10 blocks in each direction

    for pass_num in range(max_passes):
        changes = 0
        for i in range(len(blocks)):
            if _cps(blocks[i]) <= threshold:
                continue

            chars = len(blocks[i]["text"].replace("\n", ""))
            needed_dur = int(chars / threshold * 1000) + 1
            current_dur = blocks[i]["end_ms"] - blocks[i]["start_ms"]
            deficit = needed_dur - current_dur
            if deficit <= 0:
                continue

            # === Extend END: shift blocks to the right into gaps ===
            # Calculate total available slack to the right
            right_slack = 0
            for j in range(i, min(i + max_cascade, len(blocks) - 1)):
                gap = blocks[j + 1]["start_ms"] - blocks[j]["end_ms"]
                right_slack += max(0, gap - config.min_gap_ms)

            extend_right = min(deficit, right_slack)
            if extend_right > 0:
                # Cascade: shift blocks i+1, i+2, ... rightward
                # Each block shifts wholesale (same duration), consuming gap slack
                shift = extend_right
                for j in range(i + 1, min(i + 1 + max_cascade, len(blocks))):
                    if shift <= 0:
                        break
                    blocks[j]["start_ms"] += shift
                    blocks[j]["end_ms"] += shift
                    # Check gap to next block
                    if j + 1 < len(blocks):
                        gap = blocks[j + 1]["start_ms"] - blocks[j]["end_ms"]
                        if gap >= config.min_gap_ms:
                            break  # gap absorbed the shift
                        shift = config.min_gap_ms - gap  # carry forward

                # Now extend block i's end into the opened space
                blocks[i]["end_ms"] += extend_right
                deficit -= extend_right
                changes += 1

            # === Extend START: shift blocks to the left into gaps ===
            if deficit > 0:
                left_slack = 0
                for j in range(i, max(i - max_cascade, 0), -1):
                    gap = blocks[j]["start_ms"] - blocks[j - 1]["end_ms"]
                    left_slack += max(0, gap - config.min_gap_ms)
                # Also: space before first block (pre-talk silence)
                if i - max_cascade <= 0 and blocks[0]["start_ms"] > 0:
                    left_slack += blocks[0]["start_ms"]

                extend_left = min(deficit, left_slack)
                if extend_left > 0:
                    # Cascade: shift blocks i-1, i-2, ... leftward
                    shift = extend_left
                    for j in range(i - 1, -1, -1):
                        if shift <= 0:
                            break
                        blocks[j]["start_ms"] -= shift
                        blocks[j]["end_ms"] -= shift
                        # Don't go below 0
                        if blocks[j]["start_ms"] < 0:
                            overshoot = -blocks[j]["start_ms"]
                            blocks[j]["start_ms"] = 0
                            blocks[j]["end_ms"] += overshoot
                            shift -= overshoot
                        # Check gap to previous block
                        if j > 0:
                            gap = blocks[j]["start_ms"] - blocks[j - 1]["end_ms"]
                            if gap >= config.min_gap_ms:
                                break  # gap absorbed the shift
                            shift = config.min_gap_ms - gap  # carry forward

                    # Extend block i's start into the opened space
                    blocks[i]["start_ms"] -= extend_left
                    deficit -= extend_left
                    changes += 1

        if changes == 0:
            break
        print(f"  Pass {pass_num + 1}: {changes} CPS adjustments")

    # Report remaining violations
    remaining = sum(1 for b in blocks if _cps(b) > threshold)
    if remaining:
        print(f"  {remaining} blocks still have CPS > {threshold} (unfixable — no nearby silence)")

    return blocks


def build_srt(mapping_path, output_path, report_path=None):
    """Full pipeline: parse → balance CPS → duration → pad → gaps → write SRT.

    CPS balancing and duration enforcement run FIRST on raw speech blocks,
    where real silence gaps are available. Padding runs AFTER, extending
    remaining silence for readability.
    """
    config = OptimizeConfig()

    print(f"Parsing mapping: {mapping_path}")
    blocks = parse_mapping(mapping_path)
    if not blocks:
        print("ERROR: No blocks parsed from mapping file")
        sys.exit(1)

    total = len(blocks)
    print(f"  {total} blocks parsed")
    print(f"  Time range: {ms_to_time(blocks[0]['start_ms'])} → {ms_to_time(blocks[-1]['end_ms'])}")

    # Phase 1: Fix timing issues using raw silence gaps
    print("Balancing CPS (hard max ≤20)...")
    blocks = balance_cps(blocks, config, threshold=config.hard_max_cps)

    print("Balancing CPS (target ≤15)...")
    blocks = balance_cps(blocks, config, threshold=config.target_cps)

    print("Enforcing minimum duration (≥1200ms)...")
    blocks = enforce_duration(blocks, config)

    # Phase 2: Pad remaining silence for readability
    print("Applying padding (capped at max duration)...")
    blocks = apply_padding(blocks, config)

    print("Enforcing gaps (≥80ms)...")
    blocks = enforce_gaps(blocks, config)

    # Write SRT
    print(f"Writing SRT: {output_path}")
    write_srt(blocks, output_path)

    # Summary
    from .srt_utils import calc_stats

    stats = calc_stats(blocks, config)
    summary = [
        f"Build complete: {total} blocks",
        f"  Time range: {ms_to_time(blocks[0]['start_ms'])} → {ms_to_time(blocks[-1]['end_ms'])}",
        f"  CPS: avg={stats['avg_cps']:.1f}, median={stats['median_cps']:.1f}, max={stats['max_cps']:.1f}",
        f"  CPS > {config.target_cps}: {stats['cps_over_target']}",
        f"  CPS > {config.hard_max_cps}: {stats['cps_over_hard']}",
        f"  CPL > {config.max_cpl}: {stats['cpl_over_max']}",
        f"  Duration < {config.min_duration_ms}ms: {stats['duration_under_min']}",
        f"  Duration > {config.max_duration_ms}ms: {stats['duration_over_max']}",
        f"  Gaps < {config.min_gap_ms}ms: {stats['gap_under_min']}",
        f"  Overlaps: {stats['overlaps']}",
    ]
    for line in summary:
        print(line)

    if report_path:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(summary))
        print(f"  Report saved to: {report_path}")


def main():
    parser = argparse.ArgumentParser(description="Build SRT from agent mapping file")
    parser.add_argument("--mapping", required=True, help="Path to mapping file (pipe-separated)")
    parser.add_argument("--output", required=True, help="Path for output SRT file")
    parser.add_argument("--report", help="Path for build report (optional)")
    args = parser.parse_args()

    build_srt(args.mapping, args.output, args.report)


if __name__ == "__main__":
    main()
