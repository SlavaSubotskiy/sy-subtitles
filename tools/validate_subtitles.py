"""SRT subtitle validator.

Validates Ukrainian subtitles against the source transcript and whisper data.
Generates a report with statistics and quality checks.

Usage:
    python -m tools.validate_subtitles \
      --srt PATH \
      --transcript PATH \
      [--whisper-json PATH] \
      [--skip-text-check] \
      [--skip-time-check] \
      --report PATH
"""

import argparse
import re
import unicodedata

from .config import OptimizeConfig
from .srt_utils import (
    calc_stats,
    format_stats,
    load_whisper_json,
    ms_to_time,
    parse_srt,
)


def normalize_text(text):
    """Normalize text for comparison: collapse whitespace, strip punctuation dashes."""
    # NFKC normalize unicode
    text = unicodedata.normalize("NFKC", text)
    # Replace all whitespace (including newlines) with single space
    text = re.sub(r"\s+", " ", text)
    # Strip leading/trailing
    text = text.strip()
    return text


def extract_words(text):
    """Extract word tokens from text, ignoring punctuation-only tokens."""
    normalized = normalize_text(text)
    # Split on whitespace, keep only tokens that contain at least one letter or digit
    tokens = normalized.split()
    return [t for t in tokens if re.search(r"[\w]", t)]


def check_text_preservation(srt_blocks, transcript_path, report):
    """Check that all transcript text appears in SRT and vice versa."""
    with open(transcript_path, encoding="utf-8") as f:
        transcript_text = f.read()

    srt_text = " ".join(b["text"] for b in srt_blocks)

    transcript_norm = normalize_text(transcript_text)
    srt_norm = normalize_text(srt_text)

    transcript_words = extract_words(transcript_text)
    srt_words = extract_words(srt_text)

    report.append("")
    report.append("=" * 60)
    report.append("  CHECK 1: Text preservation")
    report.append("=" * 60)

    # Exact normalized match
    exact_match = transcript_norm == srt_norm

    # Word-level comparison
    words_match = transcript_words == srt_words

    report.append(f"  Transcript chars: {len(transcript_norm)}")
    report.append(f"  SRT chars: {len(srt_norm)}")
    report.append(f"  Exact normalized match: {'OK' if exact_match else 'MISMATCH'}")
    report.append(f"  Transcript words: {len(transcript_words)}")
    report.append(f"  SRT words: {len(srt_words)}")
    report.append(f"  Word-level match: {'OK' if words_match else 'MISMATCH'}")

    if not words_match:
        # Find missing and extra words
        # Use sequential comparison to find first divergence
        min_len = min(len(transcript_words), len(srt_words))
        first_diff = min_len
        for i in range(min_len):
            if transcript_words[i] != srt_words[i]:
                first_diff = i
                break

        if first_diff < min_len:
            ctx_start = max(0, first_diff - 3)
            ctx_end = min(min_len, first_diff + 4)
            report.append(f"\n  First difference at word {first_diff}:")
            report.append(f"    Transcript: ...{' '.join(transcript_words[ctx_start:ctx_end])}...")
            report.append(f"    SRT:        ...{' '.join(srt_words[ctx_start:ctx_end])}...")
        elif len(transcript_words) != len(srt_words):
            report.append(f"\n  Texts match up to word {min_len}, then differ in length")
            if len(transcript_words) > len(srt_words):
                missing = transcript_words[min_len : min_len + 10]
                report.append(f"    Missing from SRT: {' '.join(missing)}...")
            else:
                extra = srt_words[min_len : min_len + 10]
                report.append(f"    Extra in SRT: {' '.join(extra)}...")

    return words_match


def check_overlaps(srt_blocks, report):
    """Check that no blocks overlap in time."""
    report.append("")
    report.append("=" * 60)
    report.append("  CHECK 2: Timing overlaps")
    report.append("=" * 60)

    overlaps = []
    for i in range(1, len(srt_blocks)):
        prev = srt_blocks[i - 1]
        curr = srt_blocks[i]
        if prev["end_ms"] > curr["start_ms"]:
            overlap_ms = prev["end_ms"] - curr["start_ms"]
            overlaps.append((i, overlap_ms))

    report.append(f"  Overlapping blocks: {len(overlaps)}")
    if overlaps:
        for idx, overlap_ms in overlaps[:10]:
            prev = srt_blocks[idx - 1]
            curr = srt_blocks[idx]
            report.append(
                f"    #{prev['idx']}→#{curr['idx']}: "
                f"{ms_to_time(prev['end_ms'])} > {ms_to_time(curr['start_ms'])} "
                f"(overlap {overlap_ms}ms)"
            )
        if len(overlaps) > 10:
            report.append(f"    ... and {len(overlaps) - 10} more")

    return len(overlaps) == 0


def check_time_range(srt_blocks, whisper_segments, report):
    """Check that all blocks fall within whisper time range."""
    report.append("")
    report.append("=" * 60)
    report.append("  CHECK 3: Time range (vs whisper)")
    report.append("=" * 60)

    if not whisper_segments:
        report.append("  Skipped (no whisper data)")
        return True

    whisper_start_ms = int(whisper_segments[0]["start"] * 1000)
    whisper_end_ms = int(whisper_segments[-1]["end"] * 1000)

    srt_start_ms = srt_blocks[0]["start_ms"] if srt_blocks else 0
    srt_end_ms = srt_blocks[-1]["end_ms"] if srt_blocks else 0

    report.append(f"  Whisper range: {ms_to_time(whisper_start_ms)} — {ms_to_time(whisper_end_ms)}")
    report.append(f"  SRT range:     {ms_to_time(srt_start_ms)} — {ms_to_time(srt_end_ms)}")

    # Allow 2s tolerance before first speech and after last speech
    tolerance_ms = 2000
    before_speech = srt_start_ms < whisper_start_ms - tolerance_ms
    after_speech = srt_end_ms > whisper_end_ms + tolerance_ms

    if before_speech:
        report.append(f"  WARNING: SRT starts {whisper_start_ms - srt_start_ms}ms before speech")
    if after_speech:
        report.append(f"  WARNING: SRT ends {srt_end_ms - whisper_end_ms}ms after speech")

    ok = not before_speech and not after_speech
    report.append(f"  Time range: {'OK' if ok else 'WARNING'}")
    return ok


def check_sequential_numbering(srt_blocks, report):
    """Check that blocks are numbered 1, 2, 3..."""
    report.append("")
    report.append("=" * 60)
    report.append("  CHECK 4: Sequential numbering")
    report.append("=" * 60)

    errors = []
    for i, block in enumerate(srt_blocks):
        expected = i + 1
        if block["idx"] != expected:
            errors.append((expected, block["idx"]))

    report.append(f"  Total blocks: {len(srt_blocks)}")
    report.append(f"  Numbering errors: {len(errors)}")
    if errors:
        for expected, actual in errors[:10]:
            report.append(f"    Expected #{expected}, got #{actual}")
        if len(errors) > 10:
            report.append(f"    ... and {len(errors) - 10} more")

    return len(errors) == 0


def check_statistics(srt_blocks, config, report):
    """Calculate and report CPS, CPL, duration, gap statistics."""
    stats = calc_stats(srt_blocks, config)

    report.append("")
    report.append(format_stats(stats, "SUBTITLE STATISTICS"))

    # Worst CPS blocks
    report.append("")
    report.append("  Worst CPS blocks (top 10):")
    cps_list = []
    for b in srt_blocks:
        dur_s = (b["end_ms"] - b["start_ms"]) / 1000.0
        chars = len(b["text"].replace("\n", ""))
        cps = chars / dur_s if dur_s > 0 else 999
        cps_list.append((b["idx"], cps, chars, dur_s, b["text"]))

    cps_list.sort(key=lambda x: -x[1])
    for idx, cps, chars, dur, text in cps_list[:10]:
        text_short = text[:60].replace("\n", " ")
        if len(text) > 60:
            text_short += "..."
        report.append(f'    #{idx}: CPS={cps:.1f} ({chars}ch/{dur:.1f}s) "{text_short}"')

    return stats


def validate(
    srt_path,
    transcript_path,
    whisper_json_path=None,
    report_path=None,
    skip_text_check=False,
    skip_time_check=False,
    skip_cps_check=False,
    skip_duration_check=False,
):
    """Run all validation checks and write report.

    Returns (passed: bool, report_lines: list[str]).
    """
    config = OptimizeConfig()
    report = []

    report.append("=" * 60)
    report.append("  SUBTITLE VALIDATION REPORT")
    report.append("=" * 60)
    report.append(f"  SRT: {srt_path}")
    report.append(f"  Transcript: {transcript_path}")
    if whisper_json_path:
        report.append(f"  Whisper: {whisper_json_path}")

    # Parse inputs
    srt_blocks = parse_srt(srt_path)
    report.append(f"  SRT blocks: {len(srt_blocks)}")

    whisper_segments = None
    if whisper_json_path:
        whisper_segments = load_whisper_json(whisper_json_path)
        report.append(f"  Whisper segments: {len(whisper_segments)}")

    if skip_text_check:
        report.append("  (text preservation check skipped — offset video)")
    if skip_time_check:
        report.append("  (time range check skipped — offset video)")
    if skip_cps_check:
        report.append("  (CPS hard fail skipped — builder mode)")
    if skip_duration_check:
        report.append("  (duration hard fail skipped — builder mode)")

    # Run checks
    text_ok = True if skip_text_check else check_text_preservation(srt_blocks, transcript_path, report)
    overlap_ok = check_overlaps(srt_blocks, report)
    time_ok = (
        True
        if skip_time_check
        else (check_time_range(srt_blocks, whisper_segments, report) if whisper_segments else True)
    )
    numbering_ok = check_sequential_numbering(srt_blocks, report)
    stats = check_statistics(srt_blocks, config, report)

    # Summary
    report.append("")
    report.append("=" * 60)
    report.append("  SUMMARY")
    report.append("=" * 60)
    checks = [
        ("Text preservation", text_ok),
        ("No overlaps", overlap_ok),
        ("Time range", time_ok),
        ("Sequential numbering", numbering_ok),
        (f"CPL ≤ {config.max_cpl}", stats["cpl_over_max"] == 0),
        (f"Gap ≥ {config.min_gap_ms}ms", stats["gap_under_min"] == 0),
    ]
    if not skip_duration_check:
        checks.append((f"Duration ≥ {config.min_duration_ms}ms", stats["duration_under_min"] == 0))
        checks.append((f"Duration ≤ {config.max_duration_ms}ms", stats["duration_over_max"] == 0))
    if not skip_cps_check:
        checks.append((f"CPS ≤ {config.hard_max_cps}", stats["cps_over_hard"] == 0))
    all_passed = True
    for name, passed in checks:
        status = "PASS" if passed else "FAIL"
        report.append(f"  [{status}] {name}")
        if not passed:
            all_passed = False

    # Quality metrics (informational)
    report.append("")
    report.append(f"  Avg CPS: {stats['avg_cps']:.1f} (target ≤{config.target_cps})")
    report.append(f"  CPS > {config.target_cps}: {stats['cps_over_target']} blocks")
    report.append(f"  CPS > {config.hard_max_cps}: {stats['cps_over_hard']} blocks")
    report.append(f"  CPL > {config.max_cpl}: {stats['cpl_over_max']} blocks")
    report.append(f"  Duration < {config.min_duration_ms}ms: {stats['duration_under_min']} blocks")
    report.append(f"  Duration > {config.max_duration_ms}ms: {stats['duration_over_max']} blocks")
    report.append(f"  Gaps < {config.min_gap_ms}ms: {stats['gap_under_min']} blocks")

    report.append("")
    report.append(f"  Overall: {'PASSED' if all_passed else 'FAILED'}")

    if report_path:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(report))
        report.append(f"  Report saved to: {report_path}")

    return all_passed, report


def main():
    parser = argparse.ArgumentParser(description="Validate SRT subtitles")
    parser.add_argument("--srt", required=True, help="SRT file to validate")
    parser.add_argument("--transcript", required=True, help="Source transcript for text comparison")
    parser.add_argument("--whisper-json", help="Whisper JSON for time range check")
    parser.add_argument("--report", required=True, help="Output report file")
    parser.add_argument(
        "--skip-text-check",
        action="store_true",
        help="Skip text preservation check (for offset-applied videos with different duration)",
    )
    parser.add_argument(
        "--skip-time-check",
        action="store_true",
        help="Skip time range check (for offset-applied videos that extend beyond whisper range)",
    )
    parser.add_argument(
        "--skip-cps-check",
        action="store_true",
        help="Skip CPS hard fail (for builder mode — CPS is handled by build_srt)",
    )
    parser.add_argument(
        "--skip-duration-check",
        action="store_true",
        help="Skip duration hard fail (for builder mode — duration is handled by build_srt)",
    )
    args = parser.parse_args()

    passed, report = validate(
        args.srt,
        args.transcript,
        args.whisper_json,
        args.report,
        skip_text_check=args.skip_text_check,
        skip_time_check=args.skip_time_check,
        skip_cps_check=args.skip_cps_check,
        skip_duration_check=args.skip_duration_check,
    )
    for line in report:
        print(line)

    if not passed:
        exit(1)


if __name__ == "__main__":
    main()
