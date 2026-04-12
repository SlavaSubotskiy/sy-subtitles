"""Local pipeline dry-run driver.

Runs the Python half of the subtitle pipeline end-to-end without touching
Claude Code Action, GitHub runners, or any network. Instead of live LLM
build-chunks it accepts a pre-captured uk.map fixture (the exact format
the LLM would emit) and drives the rest of the pipeline locally:

    validate_artifacts (pre)  →  build_srt  →  optimize_srt  →
    validate_subtitles        →  writes a report

Usage:
    python -m tools.pipeline_dryrun \\
        --talk-dir talks/1988-05-08_Sahasrara-Puja-How-it-was-decided \\
        --video-slug Sahasrara-Puja-Talk \\
        --uk-map tests/fixtures/llm_responses/1988_sahasrara.uk.map

Exit code:
    0 — all phases passed, dryrun report written to stdout
    1 — any phase failed; error written to stderr
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .build_srt import build_srt
from .optimize_srt import optimize
from .schemas import SchemaError, validate_meta_yaml, validate_whisper_json
from .uk_map import UkMapError, validate_uk_map
from .validate_subtitles import validate


@dataclass
class PhaseResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class DryrunReport:
    phases: list[PhaseResult] = field(default_factory=list)

    def add(self, phase: PhaseResult) -> None:
        self.phases.append(phase)
        status = "OK  " if phase.ok else "FAIL"
        print(f"[{status}] {phase.name}" + (f" — {phase.detail}" if phase.detail else ""))

    @property
    def ok(self) -> bool:
        return all(p.ok for p in self.phases)


def _phase(name: str, report: DryrunReport, fn) -> bool:
    try:
        detail = fn() or ""
        report.add(PhaseResult(name, True, detail))
        return True
    except (SchemaError, UkMapError, AssertionError, ValueError, FileNotFoundError) as e:
        report.add(PhaseResult(name, False, str(e)))
        return False


def run_dryrun(
    talk_dir: Path,
    video_slug: str,
    uk_map_fixture: Path,
    work_dir: Path | None = None,
) -> DryrunReport:
    """Run the Python-side pipeline locally and return a phase report."""
    report = DryrunReport()

    work = work_dir or Path(tempfile.mkdtemp(prefix="pipeline_dryrun_"))
    work.mkdir(parents=True, exist_ok=True)
    print(f"Dryrun work dir: {work}")

    meta_path = talk_dir / "meta.yaml"
    transcript_path = talk_dir / "transcript_uk.txt"
    whisper_path = talk_dir / video_slug / "source" / "whisper.json"

    if not _phase("meta.yaml schema", report, lambda: validate_meta_yaml(str(meta_path)) and None):
        return report
    if not _phase("whisper.json schema", report, lambda: validate_whisper_json(str(whisper_path)) and None):
        return report
    if not transcript_path.is_file():
        report.add(PhaseResult("transcript_uk.txt present", False, f"missing: {transcript_path}"))
        return report
    report.add(PhaseResult("transcript_uk.txt present", True))

    # Stage fixture as if it were the live LLM output.
    staged_map = work / "uk.map"
    shutil.copy(uk_map_fixture, staged_map)

    if not _phase(
        "uk.map contract",
        report,
        lambda: f"{len(validate_uk_map(str(staged_map)))} blocks",
    ):
        return report

    built = work / "built.srt"
    build_report = work / "build_report.txt"
    if not _phase(
        "build_srt",
        report,
        lambda: build_srt(str(staged_map), str(built), str(build_report)) or f"→ {built.name}",
    ):
        return report

    optimized = work / "optimized.srt"
    if not _phase(
        "optimize_srt",
        report,
        lambda: optimize(str(built), str(whisper_path), str(optimized)) and f"→ {optimized.name}",
    ):
        return report

    def _run_validate() -> str:
        passed, lines = validate(
            str(optimized),
            str(transcript_path),
            whisper_json_path=str(whisper_path),
            skip_time_check=True,
        )
        if not passed:
            raise AssertionError("validate_subtitles failed:\n" + "\n".join(lines[-30:]))
        return "all checks passed"

    _phase("validate_subtitles", report, _run_validate)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Local pipeline dry-run driver")
    parser.add_argument("--talk-dir", required=True, help="Path to talks/{talk_id}")
    parser.add_argument("--video-slug", required=True, help="Video slug inside the talk dir")
    parser.add_argument(
        "--uk-map",
        required=True,
        help="Captured uk.map fixture that stands in for LLM build-chunks output",
    )
    parser.add_argument(
        "--work-dir",
        help="Directory for intermediate artifacts (default: temp dir, kept on failure)",
    )
    args = parser.parse_args()

    talk_dir = Path(args.talk_dir)
    work_dir = Path(args.work_dir) if args.work_dir else None

    report = run_dryrun(
        talk_dir=talk_dir,
        video_slug=args.video_slug,
        uk_map_fixture=Path(args.uk_map),
        work_dir=work_dir,
    )

    print()
    print("=" * 60)
    print(f"  DRYRUN {'PASSED' if report.ok else 'FAILED'}")
    print("=" * 60)
    if not report.ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
