"""CLI validator called from pipeline phases to enforce artifact contracts.

Usage:
    python -m tools.validate_artifacts --whisper path/to/whisper.json
    python -m tools.validate_artifacts --meta path/to/meta.yaml
    python -m tools.validate_artifacts --uk-map path/to/uk.map
    python -m tools.validate_artifacts --talk-dir talks/1988-05-08_X  # all of the above

Exits non-zero on the first failure with a clear message — drop it into a
workflow step right after the phase that produces the artifact and bad
outputs never propagate.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .schemas import SchemaError, validate_meta_yaml, validate_whisper_json
from .uk_map import UkMapError, validate_uk_map


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


def _check_uk_map(path: str) -> None:
    try:
        validate_uk_map(path)
    except UkMapError as e:
        _fail(str(e))
    print(f"OK: uk.map {path}")


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
        m = video_dir / "work" / "uk.map"
        if m.is_file():
            _check_uk_map(str(m))


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate pipeline artifacts")
    parser.add_argument("--whisper", help="Path to whisper.json")
    parser.add_argument("--meta", help="Path to meta.yaml")
    parser.add_argument("--uk-map", dest="uk_map", help="Path to uk.map")
    parser.add_argument("--talk-dir", help="Validate every artifact under a talk dir")
    args = parser.parse_args()

    if not any([args.whisper, args.meta, args.uk_map, args.talk_dir]):
        parser.error("at least one of --whisper/--meta/--uk-map/--talk-dir is required")

    if args.whisper:
        _check_whisper(args.whisper)
    if args.meta:
        _check_meta(args.meta)
    if args.uk_map:
        _check_uk_map(args.uk_map)
    if args.talk_dir:
        _check_talk_dir(args.talk_dir)


if __name__ == "__main__":
    main()
