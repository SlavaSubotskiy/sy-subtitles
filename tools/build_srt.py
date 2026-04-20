"""Apply timing pipeline to pre-merged blocks and write SRT.

Consumes blocks as list of dicts with {idx, start_ms, end_ms, text} —
produced by build_map.cmd_assemble (timecodes.txt + uk_blocks.json merged
in memory).

This module has no CLI entry point — it's called from tools.build_map.
"""

import sys

from .config import OptimizeConfig
from .srt_utils import ms_to_time, write_srt


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


def _cps(block):
    """Calculate CPS for a block."""
    dur_s = (block["end_ms"] - block["start_ms"]) / 1000.0
    if dur_s <= 0:
        return 999
    return len(block["text"].replace("\n", "")) / dur_s


def _extend_block(blocks, i, deficit, config, max_cascade=10):
    """Extend block i by deficit ms using cascade shifting.

    Shifts neighbors wholesale into nearby silence gaps (up to max_cascade
    blocks in each direction). Tries rightward first, then leftward.
    Returns remaining deficit (0 = fully resolved).
    """
    # === Extend END: shift blocks to the right into gaps ===
    right_slack = 0
    for j in range(i, min(i + max_cascade, len(blocks) - 1)):
        gap = blocks[j + 1]["start_ms"] - blocks[j]["end_ms"]
        right_slack += max(0, gap - config.min_gap_ms)

    extend_right = min(deficit, right_slack)
    if extend_right > 0:
        shift = extend_right
        for j in range(i + 1, min(i + 1 + max_cascade, len(blocks))):
            if shift <= 0:
                break
            blocks[j]["start_ms"] += shift
            blocks[j]["end_ms"] += shift
            if j + 1 < len(blocks):
                gap = blocks[j + 1]["start_ms"] - blocks[j]["end_ms"]
                if gap >= config.min_gap_ms:
                    break
                shift = config.min_gap_ms - gap

        blocks[i]["end_ms"] += extend_right
        deficit -= extend_right

    # === Extend START: shift blocks to the left into gaps ===
    if deficit > 0:
        left_slack = 0
        for j in range(i, max(i - max_cascade, 0), -1):
            gap = blocks[j]["start_ms"] - blocks[j - 1]["end_ms"]
            left_slack += max(0, gap - config.min_gap_ms)
        if i - max_cascade <= 0 and blocks[0]["start_ms"] > 0:
            left_slack += blocks[0]["start_ms"]

        extend_left = min(deficit, left_slack)
        if extend_left > 0:
            shift = extend_left
            for j in range(i - 1, -1, -1):
                if shift <= 0:
                    break
                blocks[j]["start_ms"] -= shift
                blocks[j]["end_ms"] -= shift
                if blocks[j]["start_ms"] < 0:
                    overshoot = -blocks[j]["start_ms"]
                    blocks[j]["start_ms"] = 0
                    blocks[j]["end_ms"] += overshoot
                    shift -= overshoot
                if j > 0:
                    gap = blocks[j]["start_ms"] - blocks[j - 1]["end_ms"]
                    if gap >= config.min_gap_ms:
                        break
                    shift = config.min_gap_ms - gap

            blocks[i]["start_ms"] -= extend_left
            deficit -= extend_left

    return deficit


def enforce_duration(blocks, config=None):
    """Extend blocks shorter than min_duration using cascade shifting.

    Shifts neighbors into nearby silence gaps to make room.
    Reports blocks that remain unfixable.
    """
    if config is None:
        config = OptimizeConfig()

    warnings = []

    for i in range(len(blocks)):
        duration = blocks[i]["end_ms"] - blocks[i]["start_ms"]
        if duration >= config.min_duration_ms:
            continue

        deficit = config.min_duration_ms - duration

        # Last block — just extend freely
        if i == len(blocks) - 1:
            blocks[i]["end_ms"] = blocks[i]["start_ms"] + config.min_duration_ms
            continue

        remaining = _extend_block(blocks, i, deficit, config)
        if remaining > 0:
            new_dur = blocks[i]["end_ms"] - blocks[i]["start_ms"]
            warnings.append(f"  Short block #{blocks[i]['idx']}: {new_dur}ms < {config.min_duration_ms}ms (unfixable)")

    for w in warnings:
        print(w)

    return blocks


def balance_cps(blocks, config=None, threshold=None):
    """Balance CPS by shifting neighbors into nearby silence (gaps).

    Uses cascade shifting: finds gaps in the neighborhood (up to 10 blocks),
    shifts intermediate blocks wholesale (preserving their duration),
    and extends the high-CPS block into the opened space.
    """
    if config is None:
        config = OptimizeConfig()
    if threshold is None:
        threshold = config.hard_max_cps

    max_passes = 10

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

            remaining = _extend_block(blocks, i, deficit, config)
            if remaining < deficit:
                changes += 1

        if changes == 0:
            break
        print(f"  Pass {pass_num + 1}: {changes} CPS adjustments")

    remaining = sum(1 for b in blocks if _cps(b) > threshold)
    if remaining:
        print(f"  {remaining} blocks still have CPS > {threshold} (unfixable — no nearby silence)")

    return blocks


def build_srt_from_blocks(blocks, output_path, report_path=None):
    """Full timing pipeline on in-memory blocks.

    blocks: list of dicts with keys {idx, start_ms, end_ms, text}.
    Runs: gaps(raw) → CPS → duration → CPS(soft) → pad → gaps → write SRT.
    """
    config = OptimizeConfig()

    if not blocks:
        print("ERROR: No blocks provided")
        sys.exit(1)

    total = len(blocks)
    print(f"  {total} blocks parsed")
    print(f"  Time range: {ms_to_time(blocks[0]['start_ms'])} → {ms_to_time(blocks[-1]['end_ms'])}")

    # Phase 0: Fix raw mapping overlaps (agent errors)
    print("Fixing raw overlaps...")
    blocks = enforce_gaps(blocks, config)

    # Phase 1: Fix timing issues using clean silence gaps
    print("Balancing CPS (hard max ≤20)...")
    blocks = balance_cps(blocks, config, threshold=config.hard_max_cps)

    print("Enforcing minimum duration (≥1200ms)...")
    blocks = enforce_duration(blocks, config)

    print("Balancing CPS (target ≤15)...")
    blocks = balance_cps(blocks, config, threshold=config.target_cps)

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
