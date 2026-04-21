"""Dry-run pipeline matrix — runs the full Python side of subtitle-pipeline
on every bootstrapped snapshot with fake LLM responses, then verifies the
resulting SRT against the snapshot's expected artifacts.

This is the local counterpart to the GitHub Actions matrix driver. Each
snapshot cell takes ~2-5 seconds; the whole suite runs in ~60s even for
17 talks. Any regression in build_map, build_srt, optimize_srt, generate_map,
or the fake_llm → verify_snapshot plumbing shows up here instantly.

Tests are parametrized over every pipeline_snapshots/* discovered at
collection time, so adding a new bootstrap snapshot automatically
extends coverage without editing this file.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_ROOT = ROOT / "tests" / "fixtures" / "pipeline_snapshots"


@dataclass(frozen=True)
class DryrunCase:
    name: str
    talk_id: str
    video_slug: str
    snapshot: Path


def _discover_cases() -> list[DryrunCase]:
    cases: list[DryrunCase] = []
    if not SNAPSHOT_ROOT.is_dir():
        return cases
    for talk_dir in sorted(SNAPSHOT_ROOT.iterdir()):
        if not talk_dir.is_dir() or talk_dir.name.startswith("_"):
            continue
        for video_dir in sorted(talk_dir.iterdir()):
            if not video_dir.is_dir():
                continue
            manifest = video_dir / "manifest.json"
            if not manifest.is_file():
                continue
            cases.append(
                DryrunCase(
                    name=f"{talk_dir.name}/{video_dir.name}",
                    talk_id=talk_dir.name,
                    video_slug=video_dir.name,
                    snapshot=video_dir,
                )
            )
    return cases


CASES = _discover_cases()

# The dry-run corpus is a strict subset of shipped talks that already pass
# validate_subtitles end-to-end — see tools.bootstrap_snapshot.KNOWN_GOOD_TALKS.
# No xfails here: anything in the corpus must always be green.


def _case_params():
    return [pytest.param(c, id=c.name) for c in CASES]


def test_dryrun_corpus_nonempty() -> None:
    assert CASES, "No pipeline_snapshots bootstrapped yet — run `python -m tools.bootstrap_snapshot --all`"


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, check=False)


def _run_full_pipeline(case: DryrunCase, scratch: Path) -> None:
    """Replay translate + review + build phases using fake LLM responses
    from the case's snapshot; raise on any phase error."""
    # Stage a clean copy of the talk dir in scratch/
    src_talk = ROOT / "talks" / case.talk_id
    dst_talk = scratch / case.talk_id
    shutil.copytree(src_talk, dst_talk)
    # Strip derived artifacts so the replay has to produce them.
    (dst_talk / "transcript_uk.txt").unlink(missing_ok=True)
    video_dir = dst_talk / case.video_slug
    shutil.rmtree(video_dir / "work", ignore_errors=True)
    shutil.rmtree(video_dir / "final", ignore_errors=True)

    def run(cmd: list[str], label: str) -> None:
        r = _run(cmd, cwd=ROOT)
        assert r.returncode == 0, (
            f"{label} failed for {case.name}:\n"
            f"CMD: {' '.join(cmd)}\n"
            f"STDOUT: {r.stdout[-1500:]}\n"
            f"STDERR: {r.stderr[-1500:]}"
        )

    # translate + review (fake LLM)
    run(
        [
            sys.executable,
            "-m",
            "tools.fake_llm",
            "translate",
            "--snapshot",
            str(case.snapshot),
            "--talk-dir",
            str(dst_talk),
        ],
        "fake_llm translate",
    )
    run(
        [
            sys.executable,
            "-m",
            "tools.fake_llm",
            "review",
            "--snapshot",
            str(case.snapshot),
            "--talk-dir",
            str(dst_talk),
        ],
        "fake_llm review",
    )

    # build_map prepare (real Python) — splits UK transcript into uk_blocks.json
    run(
        [
            sys.executable,
            "-m",
            "tools.build_map",
            "prepare",
            "--talk-dir",
            str(dst_talk),
            "--video-slug",
            case.video_slug,
        ],
        "build_map prepare",
    )

    # build_map prepare-timing (real Python) — builds compact timing.json
    run(
        [
            sys.executable,
            "-m",
            "tools.build_map",
            "prepare-timing",
            "--talk-dir",
            str(dst_talk),
            "--video-slug",
            case.video_slug,
        ],
        "build_map prepare-timing",
    )

    # build-timecodes (fake LLM — single pass, writes timecodes.txt)
    run(
        [
            sys.executable,
            "-m",
            "tools.fake_llm",
            "build-timecodes",
            "--snapshot",
            str(case.snapshot),
            "--work-dir",
            str(video_dir / "work"),
        ],
        "fake_llm build-timecodes",
    )

    # validate timecodes format BEFORE assemble — fail early on bad LLM output
    run(
        [
            sys.executable,
            "-m",
            "tools.validate_artifacts",
            "--timecodes",
            str(video_dir / "work" / "timecodes.txt"),
        ],
        "validate_artifacts timecodes",
    )

    # assemble — timecodes.txt + uk_blocks.json → uk.srt (in-memory merge)
    run(
        [
            sys.executable,
            "-m",
            "tools.build_map",
            "assemble",
            "--talk-dir",
            str(dst_talk),
            "--video-slug",
            case.video_slug,
        ],
        "build_map assemble",
    )

    # optimize (mirror real pipeline flags)
    srt = video_dir / "final" / "uk.srt"
    run(
        [
            sys.executable,
            "-m",
            "tools.optimize_srt",
            "--srt",
            str(srt),
            "--output",
            str(srt),
            "--skip-duration-split",
            "--skip-cps-split",
        ],
        "optimize_srt",
    )

    # verify
    run(
        [
            sys.executable,
            "-m",
            "tools.verify_snapshot",
            "--talk-dir",
            str(dst_talk),
            "--video-slug",
            case.video_slug,
            "--snapshot",
            str(case.snapshot),
        ],
        "verify_snapshot",
    )


@pytest.mark.parametrize("case", _case_params() or [pytest.param(None, id="<empty>")])
def test_dryrun_replay_all_phases(case: DryrunCase, tmp_path: Path) -> None:
    if case is None:
        pytest.skip("no snapshots")
    _run_full_pipeline(case, tmp_path)
