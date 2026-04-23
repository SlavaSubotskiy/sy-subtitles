"""CLI validator called from pipeline phases to enforce artifact contracts.

Usage:
    python -m tools.validate_artifacts --whisper path/to/whisper.json
    python -m tools.validate_artifacts --meta path/to/meta.yaml
    python -m tools.validate_artifacts --timecodes path/to/timecodes.txt [--expected-blocks N]
    python -m tools.validate_artifacts --talk-dir talks/1988-05-08_X  # all of the above

Exits non-zero on the first failure with a clear message — drop it into a
workflow step right after the phase that produces the artifact and bad
outputs never propagate.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from .schemas import SchemaError, validate_meta_yaml, validate_whisper_json

TIMECODE_RE = re.compile(r"^#(\d+)\s*\|\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\|\s*(\d{2}:\d{2}:\d{2},\d{3})\s*$")


def _fail(msg: str) -> None:
    print(f"::error::{msg}", file=sys.stderr)
    sys.exit(1)


def _check_whisper(path: str) -> None:
    try:
        validate_whisper_json(path)
    except SchemaError as e:
        _fail(str(e))
    print(f"OK: whisper {path}")


def _check_meta(path: str) -> None:
    try:
        validate_meta_yaml(path)
    except SchemaError as e:
        _fail(str(e))
    print(f"OK: meta {path}")


def _check_timecodes(
    path: str,
    expected_blocks: int | None = None,
    max_blocks: int | None = None,
    allow_skipped_ids: bool = False,
) -> None:
    p = Path(path)
    if not p.is_file():
        _fail(f"timecodes: {path} missing")

    seen_ids: set[int] = set()
    last_id = 0
    for line_no, raw in enumerate(p.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        m = TIMECODE_RE.match(line)
        if not m:
            _fail(f"timecodes {path}:{line_no}: expected '#N | HH:MM:SS,mmm | HH:MM:SS,mmm', got {line!r}")
        idx = int(m.group(1))
        if idx in seen_ids:
            _fail(f"timecodes {path}:{line_no}: duplicate block id #{idx}")
        # IDs must be strictly ascending. With `allow_skipped_ids` (en-srt
        # mode — Opus may drop UK blocks without an EN counterpart), gaps
        # are fine; without the flag (whisper mode), every id must follow
        # its predecessor exactly.
        if allow_skipped_ids:
            if idx <= last_id:
                _fail(f"timecodes {path}:{line_no}: id #{idx} not strictly after previous #{last_id}")
        else:
            if idx != last_id + 1:
                _fail(f"timecodes {path}:{line_no}: non-sequential id #{idx} (expected #{last_id + 1})")
        seen_ids.add(idx)
        last_id = idx
        start, end = m.group(2), m.group(3)
        if start >= end:
            _fail(f"timecodes {path}:{line_no}: block #{idx} start {start} >= end {end}")

    if not seen_ids:
        _fail(f"timecodes {path}: no blocks found")
    if expected_blocks is not None and len(seen_ids) != expected_blocks:
        _fail(f"timecodes {path}: got {len(seen_ids)} blocks, expected {expected_blocks}")
    if max_blocks is not None and len(seen_ids) > max_blocks:
        _fail(f"timecodes {path}: got {len(seen_ids)} blocks, exceeds max {max_blocks}")

    print(f"OK: timecodes {path} ({len(seen_ids)} blocks)")


def _check_talk_dir(talk_dir: str) -> None:
    root = Path(talk_dir)
    meta = root / "meta.yaml"
    if not meta.is_file():
        _fail(f"{meta}: missing")
    _check_meta(str(meta))
    for video_dir in sorted(root.iterdir()):
        if not video_dir.is_dir():
            continue
        w = video_dir / "source" / "whisper.json"
        if w.is_file():
            _check_whisper(str(w))
        tc = video_dir / "work" / "timecodes.txt"
        if tc.is_file():
            _check_timecodes(str(tc))


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate pipeline artifacts")
    parser.add_argument("--whisper", help="Path to whisper.json")
    parser.add_argument("--meta", help="Path to meta.yaml")
    parser.add_argument("--timecodes", help="Path to timecodes.txt")
    parser.add_argument("--expected-blocks", type=int, help="Expected number of blocks in --timecodes (exact)")
    parser.add_argument(
        "--max-blocks",
        type=int,
        help="Maximum number of blocks in --timecodes (upper bound; for en-srt mode where Opus may skip)",
    )
    parser.add_argument(
        "--allow-skipped-ids",
        action="store_true",
        help="Allow gaps in block IDs (en-srt mode — Opus may drop UK blocks without an EN counterpart)",
    )
    parser.add_argument("--talk-dir", help="Validate every artifact under a talk dir")
    args = parser.parse_args()

    if not any([args.whisper, args.meta, args.timecodes, args.talk_dir]):
        parser.error("at least one of --whisper/--meta/--timecodes/--talk-dir is required")

    if args.whisper:
        _check_whisper(args.whisper)
    if args.meta:
        _check_meta(args.meta)
    if args.timecodes:
        _check_timecodes(
            args.timecodes,
            expected_blocks=args.expected_blocks,
            max_blocks=args.max_blocks,
            allow_skipped_ids=args.allow_skipped_ids,
        )
    if args.talk_dir:
        _check_talk_dir(args.talk_dir)


if __name__ == "__main__":
    main()
