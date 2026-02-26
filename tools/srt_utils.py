"""SRT parsing, writing, and statistics utilities."""

import json
import re

from .config import OptimizeConfig


def time_to_ms(t):
    """Convert SRT time string (HH:MM:SS,mmm) to milliseconds."""
    h, m, rest = t.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600000 + int(m) * 60000 + int(s) * 1000 + int(ms)


def ms_to_time(ms):
    """Convert milliseconds to SRT time string (HH:MM:SS,mmm)."""
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_srt(filepath):
    """Parse SRT file into list of blocks.

    Each block is a dict with keys: idx, start_ms, end_ms, text.
    """
    with open(filepath, encoding="utf-8-sig") as f:
        content = f.read()

    blocks = []
    raw_blocks = re.split(r"\n\n+", content.strip())

    for raw in raw_blocks:
        lines = raw.strip().split("\n")
        if len(lines) < 3:
            continue
        try:
            idx = int(lines[0])
        except ValueError:
            continue
        time_match = re.match(
            r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})",
            lines[1],
        )
        if not time_match:
            continue
        start_ms = time_to_ms(time_match.group(1))
        end_ms = time_to_ms(time_match.group(2))
        text = "\n".join(lines[2:])
        blocks.append(
            {
                "idx": idx,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "text": text,
            }
        )

    return blocks


def write_srt(blocks, filepath):
    """Write blocks to SRT file with sequential numbering."""
    with open(filepath, "w", encoding="utf-8") as f:
        for i, b in enumerate(blocks, 1):
            f.write(f"{i}\n")
            f.write(f"{ms_to_time(b['start_ms'])} --> {ms_to_time(b['end_ms'])}\n")
            f.write(f"{b['text']}\n\n")


def load_whisper_json(filepath):
    """Load Whisper JSON and return segments list."""
    with open(filepath) as f:
        data = json.load(f)
    return data["segments"]


def calc_stats(blocks, config=None):
    """Calculate statistics for a set of SRT blocks."""
    if config is None:
        config = OptimizeConfig()

    stats = {
        "total_blocks": len(blocks),
        "cps_values": [],
        "cpl_values": [],
        "durations": [],
        "gaps": [],
        "overlaps": 0,
        "cps_over_target": 0,
        "cps_over_hard": 0,
        "cpl_over_max": 0,
        "duration_under_min": 0,
        "duration_over_max": 0,
        "gap_under_min": 0,
        "lines_over_max": 0,
        "chars_over_max": 0,
    }

    for i, b in enumerate(blocks):
        text = b["text"]
        duration_ms = b["end_ms"] - b["start_ms"]
        duration_s = duration_ms / 1000.0
        chars = len(text.replace("\n", ""))
        lines = text.split("\n")
        max_cpl = max(len(line) for line in lines)
        cps = chars / duration_s if duration_s > 0 else 999

        stats["cps_values"].append(cps)
        stats["cpl_values"].append(max_cpl)
        stats["durations"].append(duration_ms)

        if cps > config.target_cps:
            stats["cps_over_target"] += 1
        if cps > config.hard_max_cps:
            stats["cps_over_hard"] += 1
        if max_cpl > config.max_cpl:
            stats["cpl_over_max"] += 1
        if duration_ms < config.min_duration_ms:
            stats["duration_under_min"] += 1
        if duration_ms > config.max_duration_ms:
            stats["duration_over_max"] += 1
        if len(lines) > config.max_lines:
            stats["lines_over_max"] += 1
        if chars > config.max_chars_block:
            stats["chars_over_max"] += 1

        if i > 0:
            gap = b["start_ms"] - blocks[i - 1]["end_ms"]
            stats["gaps"].append(gap)
            if gap < 0:
                stats["overlaps"] += 1
            if 0 <= gap < config.min_gap_ms:
                stats["gap_under_min"] += 1

    if stats["cps_values"]:
        stats["avg_cps"] = sum(stats["cps_values"]) / len(stats["cps_values"])
        sorted_cps = sorted(stats["cps_values"])
        stats["median_cps"] = sorted_cps[len(sorted_cps) // 2]
        stats["max_cps"] = max(stats["cps_values"])
    else:
        stats["avg_cps"] = stats["median_cps"] = stats["max_cps"] = 0

    if stats["cpl_values"]:
        stats["avg_cpl"] = sum(stats["cpl_values"]) / len(stats["cpl_values"])
        stats["max_cpl"] = max(stats["cpl_values"])
    else:
        stats["avg_cpl"] = stats["max_cpl"] = 0

    return stats


def format_stats(stats, label=""):
    """Format statistics into a human-readable string."""
    lines = []
    lines.append(f"{'=' * 60}")
    lines.append(f"  {label}")
    lines.append(f"{'=' * 60}")
    lines.append(f"  Total blocks: {stats['total_blocks']}")
    lines.append(f"  CPS: avg={stats['avg_cps']:.1f}, median={stats['median_cps']:.1f}, max={stats['max_cps']:.1f}")
    lines.append(
        f"  CPS > target: {stats['cps_over_target']} ({stats['cps_over_target'] / stats['total_blocks'] * 100:.1f}%)"
    )
    lines.append(
        f"  CPS > hard max: {stats['cps_over_hard']} ({stats['cps_over_hard'] / stats['total_blocks'] * 100:.1f}%)"
    )
    lines.append(f"  CPL: avg={stats['avg_cpl']:.1f}, max={stats['max_cpl']}")
    lines.append(f"  CPL > max: {stats['cpl_over_max']} ({stats['cpl_over_max'] / stats['total_blocks'] * 100:.1f}%)")
    lines.append(
        f"  Chars > max block: {stats['chars_over_max']} ({stats['chars_over_max'] / stats['total_blocks'] * 100:.1f}%)"
    )
    lines.append(f"  Lines > max: {stats['lines_over_max']}")
    lines.append(f"  Duration < min: {stats['duration_under_min']}")
    lines.append(f"  Duration > max: {stats['duration_over_max']}")
    lines.append(f"  Overlaps: {stats['overlaps']}")
    lines.append(f"  Gaps < min: {stats['gap_under_min']}")
    return "\n".join(lines)
