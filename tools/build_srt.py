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

    For each block, extend end to: min(next_start - gap, end + 5000ms).
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

        if i < len(blocks) - 1:
            next_start = blocks[i + 1]["start_ms"]
            # Extend into silence: up to next block start minus gap
            padded_end = next_start - config.min_gap_ms
            # Cap at max padding
            padded_end = min(padded_end, original_end + max_pad_ms)
            # Never shrink below original end
            b["end_ms"] = max(padded_end, original_end)
        else:
            # Last block: modest extension
            b["end_ms"] = original_end + last_block_pad_ms

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

    Reports unfixable issues.
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
            else:
                # Last block — just extend
                b["end_ms"] = b["start_ms"] + config.min_duration_ms

            new_duration = b["end_ms"] - b["start_ms"]
            if new_duration < config.min_duration_ms:
                warnings.append(f"  Short block #{b['idx']}: {new_duration}ms < {config.min_duration_ms}ms (unfixable)")

    for w in warnings:
        print(w)

    return result


def build_srt(mapping_path, output_path, report_path=None):
    """Full pipeline: parse mapping → pad → gaps → duration → write SRT."""
    config = OptimizeConfig()

    print(f"Parsing mapping: {mapping_path}")
    blocks = parse_mapping(mapping_path)
    if not blocks:
        print("ERROR: No blocks parsed from mapping file")
        sys.exit(1)

    total = len(blocks)
    print(f"  {total} blocks parsed")
    print(f"  Time range: {ms_to_time(blocks[0]['start_ms'])} → {ms_to_time(blocks[-1]['end_ms'])}")

    # Pipeline
    print("Applying padding...")
    blocks = apply_padding(blocks, config)

    print("Enforcing gaps (≥80ms)...")
    blocks = enforce_gaps(blocks, config)

    print("Enforcing minimum duration (≥1200ms)...")
    blocks = enforce_duration(blocks, config)

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
