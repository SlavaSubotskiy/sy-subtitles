"""Stand-in for claude-code-action during a dry-run pipeline replay.

Reads canned responses from a snapshot directory (see bootstrap_snapshot)
and writes them into the work tree where the real pipeline expects them.

Usage:
    python -m tools.fake_llm translate \\
        --snapshot tests/fixtures/pipeline_snapshots/TALK/VIDEO \\
        --talk-dir talks/TALK

    python -m tools.fake_llm review \\
        --snapshot ... --talk-dir talks/TALK

    python -m tools.fake_llm build-timecodes \\
        --snapshot ... --work-dir talks/TALK/VIDEO/work

    python -m tools.fake_llm whisper \\
        --snapshot ... --output talks/TALK/VIDEO/source/whisper.json
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def _copy(src: Path, dst: Path) -> None:
    if not src.is_file():
        print(f"::error::fake_llm: snapshot missing {src}", file=sys.stderr)
        sys.exit(1)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dst)
    print(f"fake_llm: {src.name} → {dst}")


def cmd_translate(args: argparse.Namespace) -> None:
    snapshot = Path(args.snapshot)
    talk_dir = Path(args.talk_dir)
    _copy(snapshot / "transcript_uk.txt", talk_dir / "transcript_uk.txt")


def cmd_review(args: argparse.Namespace) -> None:
    snapshot = Path(args.snapshot)
    talk_dir = Path(args.talk_dir)
    _copy(snapshot / "transcript_uk.txt", talk_dir / "transcript_uk.txt")
    _copy(snapshot / "review_report.md", talk_dir / "review_report.md")


def cmd_build_timecodes(args: argparse.Namespace) -> None:
    snapshot = Path(args.snapshot)
    work_dir = Path(args.work_dir)
    _copy(snapshot / "work" / "timecodes.txt", work_dir / "timecodes.txt")


def cmd_whisper(args: argparse.Namespace) -> None:
    """Canned whisper.json output — the repo already has it, so just copy it
    from the original location into the expected path inside work tree."""
    snapshot = Path(args.snapshot)
    target = Path(args.output)
    if target.is_file():
        print(f"fake_llm whisper: {target} already present — no-op")
        return
    fallback = snapshot / "whisper.json"
    if fallback.is_file():
        _copy(fallback, target)
        return
    print(f"::error::fake_llm whisper: neither {target} nor snapshot {fallback} exist", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fake LLM responder for dry-run pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_tr = sub.add_parser("translate")
    p_tr.add_argument("--snapshot", required=True)
    p_tr.add_argument("--talk-dir", required=True)
    p_tr.set_defaults(func=cmd_translate)

    p_rv = sub.add_parser("review")
    p_rv.add_argument("--snapshot", required=True)
    p_rv.add_argument("--talk-dir", required=True)
    p_rv.set_defaults(func=cmd_review)

    p_bt = sub.add_parser("build-timecodes")
    p_bt.add_argument("--snapshot", required=True)
    p_bt.add_argument("--work-dir", required=True)
    p_bt.set_defaults(func=cmd_build_timecodes)

    p_ws = sub.add_parser("whisper")
    p_ws.add_argument("--snapshot", required=True)
    p_ws.add_argument("--output", required=True)
    p_ws.set_defaults(func=cmd_whisper)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
