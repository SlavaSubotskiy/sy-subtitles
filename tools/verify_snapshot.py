"""Verify that a dry-run pipeline produced artifacts consistent with a snapshot.

Verification is *behavioural*, not byte-identical:
  1. final/uk.srt passes validate_subtitles against expected/transcript_uk.txt
  2. transcript_uk.txt byte-equals expected (translate phase is deterministic)
  3. Block count in produced uk.srt is within ±10% of expected

Non-goals: exact timecode equality — optimize_srt has real freedom and
the fake LLM replay exercises the whole pipeline, not just the optimiser.

Usage:
    python -m tools.verify_snapshot \\
        --talk-dir talks/TALK \\
        --video-slug VIDEO \\
        --snapshot tests/fixtures/pipeline_snapshots/TALK/VIDEO \\
        --phases translate,review,build
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import OptimizeConfig
from .srt_utils import calc_stats, parse_srt
from .validate_subtitles import (
    check_overlaps,
    check_sequential_numbering,
    check_text_preservation,
)


def _fail(msg: str) -> None:
    print(f"::error::{msg}", file=sys.stderr)
    sys.exit(1)


def verify_translate(talk_dir: Path, snapshot: Path) -> None:
    produced = talk_dir / "transcript_uk.txt"
    expected = snapshot / "expected" / "transcript_uk.txt"
    if not produced.is_file():
        _fail(f"verify translate: missing {produced}")
    if not expected.is_file():
        _fail(f"verify translate: missing expected {expected}")
    p = produced.read_text(encoding="utf-8").strip()
    e = expected.read_text(encoding="utf-8").strip()
    if p != e:
        _fail(f"verify translate: transcript drifted from snapshot ({len(p)} vs {len(e)} chars)")
    print(f"  [OK] translate: {len(p)} chars match snapshot")


def verify_build(talk_dir: Path, video_slug: str, snapshot: Path) -> None:
    """Verify the build phase matches the snapshot's baseline.

    The snapshot manifest records the baseline (n_blocks, avg_cps,
    cps_over_hard, duration_under_min) captured at bootstrap time. verify
    asserts that a fresh replay produces statistics identical or very
    close to the baseline — any drift signals a regression in the Python
    pipeline, not in quality thresholds.

    Hard invariants (any failure → error):
      * Text preservation against expected transcript
      * Sequential numbering
      * No overlaps
      * Block count == baseline.n_blocks (exact)
      * Baseline stats identical (avg_cps ≤ ±0.2, counters exact)
    """
    srt = talk_dir / video_slug / "final" / "uk.srt"
    if not srt.is_file():
        _fail(f"verify build: missing {srt}")
    transcript = snapshot / "expected" / "transcript_uk.txt"
    manifest_path = snapshot / "manifest.json"
    if not manifest_path.is_file():
        _fail(f"verify build: missing manifest {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    baseline = manifest.get("baseline")
    if baseline is None:
        _fail("verify build: snapshot manifest lacks 'baseline' — re-run bootstrap_snapshot")

    blocks = parse_srt(str(srt))
    report: list[str] = []
    text_ok = check_text_preservation(blocks, str(transcript), report)
    overlap_ok = check_overlaps(blocks, report)
    numbering_ok = check_sequential_numbering(blocks, report)
    stats = calc_stats(blocks, OptimizeConfig())

    if not text_ok:
        _fail("verify build: text preservation failed — shipped text drift")
    if not overlap_ok:
        _fail("verify build: overlaps detected")
    if not numbering_ok:
        _fail("verify build: non-sequential block numbering")

    drift: list[str] = []
    if len(blocks) != baseline["n_blocks"]:
        drift.append(f"n_blocks: {len(blocks)} vs baseline {baseline['n_blocks']}")
    if abs(float(stats["avg_cps"]) - float(baseline["avg_cps"])) > 0.2:
        drift.append(f"avg_cps: {stats['avg_cps']:.2f} vs baseline {baseline['avg_cps']}")
    if int(stats["cps_over_hard"]) != baseline["cps_over_hard"]:
        drift.append(f"cps_over_hard: {stats['cps_over_hard']} vs baseline {baseline['cps_over_hard']}")
    if int(stats["duration_under_min"]) != baseline["duration_under_min"]:
        drift.append(f"duration_under_min: {stats['duration_under_min']} vs baseline {baseline['duration_under_min']}")
    if drift:
        _fail("verify build: baseline drift — " + "; ".join(drift))

    print(
        f"  [OK] build: {len(blocks)} blocks (baseline-matched); "
        f"avg CPS={stats['avg_cps']:.1f}; CPS>20={stats['cps_over_hard']}; "
        f"dur<min={stats['duration_under_min']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify dry-run against snapshot")
    parser.add_argument("--talk-dir", required=True)
    parser.add_argument("--video-slug", required=True)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument(
        "--phases",
        default="translate,build",
        help="Comma-separated phases to verify (translate, build).",
    )
    args = parser.parse_args()

    talk_dir = Path(args.talk_dir)
    snapshot = Path(args.snapshot)
    phases = [p.strip() for p in args.phases.split(",") if p.strip()]

    print(f"verify_snapshot: {talk_dir.name}/{args.video_slug}")
    if "translate" in phases:
        verify_translate(talk_dir, snapshot)
    if "build" in phases:
        verify_build(talk_dir, args.video_slug, snapshot)

    print("verify_snapshot: all phases passed")


if __name__ == "__main__":
    main()
