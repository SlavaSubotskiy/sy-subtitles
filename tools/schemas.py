"""Artifact-boundary schema validators.

Every non-trivial file that crosses a pipeline phase boundary has a strict
contract enforced here. Call the validators directly from pipeline steps
(`python -m tools.validate_artifacts ...`) so contract violations fail loud
in the fastest-failing phase instead of mutating into silent bad SRTs.

Schemas covered:
  * whisper.json — speech-detection output shared with build_map/align_uk
  * meta.yaml    — talk manifest, consumed by every workflow

uk.map has its own dedicated validator (tools.uk_map) because the format
has richer invariants and a non-strict fallback path.
"""

from __future__ import annotations

import json
from typing import Any

import yaml

from .workflow_validation import (
    InvalidWorkflowInput,
    validate_talk_id,
    validate_video_slug,
    validate_vimeo_url,
)


class SchemaError(ValueError):
    def __init__(self, source: str, path: str, message: str) -> None:
        super().__init__(f"{source} {path}: {message}")
        self.source = source
        self.path = path
        self.message = message


def _require(obj: Any, key: str, expected_type: type, source: str, path: str) -> Any:
    if not isinstance(obj, dict):
        raise SchemaError(source, path, f"expected object, got {type(obj).__name__}")
    if key not in obj:
        raise SchemaError(source, path, f"missing required field '{key}'")
    value = obj[key]
    if not isinstance(value, expected_type):
        raise SchemaError(
            source,
            f"{path}.{key}",
            f"expected {expected_type.__name__}, got {type(value).__name__}",
        )
    return value


# ---------------------------------------------------------------------------
# whisper.json
# ---------------------------------------------------------------------------


def validate_whisper_json(path: str) -> dict:
    """Validate a whisper.json file and return its parsed contents."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise SchemaError("whisper.json", path, f"cannot read/parse: {e}") from None

    # `language` is informational — older whisper outputs omitted it and the
    # downstream tools tolerate absence, so we only type-check when present.
    if "language" in data and not isinstance(data["language"], str):
        raise SchemaError("whisper.json", path, "language must be a string when present")
    segments = _require(data, "segments", list, "whisper.json", "")

    if not segments:
        raise SchemaError("whisper.json", path, "segments[] is empty")

    prev_end = -1.0
    for i, seg in enumerate(segments):
        seg_path = f"segments[{i}]"
        if not isinstance(seg, dict):
            raise SchemaError("whisper.json", path, f"{seg_path} is not an object")
        start = _require(seg, "start", (int, float), "whisper.json", seg_path)
        end = _require(seg, "end", (int, float), "whisper.json", seg_path)
        _require(seg, "text", str, "whisper.json", seg_path)
        if start < 0:
            raise SchemaError("whisper.json", path, f"{seg_path}.start={start} negative")
        if end < start:
            raise SchemaError("whisper.json", path, f"{seg_path}: end {end} < start {start}")
        # Whisper legitimately produces overlapping segments (multi-speaker,
        # silence trimming, VAD re-ordering). Only flag *catastrophic* rewinds
        # that indicate a corrupt file.
        if start < prev_end - 20.0:
            raise SchemaError(
                "whisper.json",
                path,
                f"{seg_path}.start={start} < previous end={prev_end} (backward jump > 20s)",
            )
        prev_end = max(prev_end, end)

        words = seg.get("words", [])
        if not isinstance(words, list):
            raise SchemaError("whisper.json", path, f"{seg_path}.words must be a list")
        for j, w in enumerate(words):
            w_path = f"{seg_path}.words[{j}]"
            if not isinstance(w, dict):
                raise SchemaError("whisper.json", path, f"{w_path} is not an object")
            if "word" not in w or not isinstance(w["word"], str):
                raise SchemaError("whisper.json", path, f"{w_path}.word missing")
            if "start" in w and "end" in w and w["end"] < w["start"]:
                raise SchemaError("whisper.json", path, f"{w_path}: end < start")

    return data


# ---------------------------------------------------------------------------
# meta.yaml
# ---------------------------------------------------------------------------

ALLOWED_LANGUAGES = frozenset({"en", "hi", "mr", "fr", "it", "es", "de", "pt", "ru"})
DATE_RE_LEN = 10  # YYYY-MM-DD


def validate_meta_yaml(path: str) -> dict:
    """Validate a talk meta.yaml and return its parsed contents."""
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        raise SchemaError("meta.yaml", path, f"cannot read/parse: {e}") from None

    if not isinstance(data, dict):
        raise SchemaError("meta.yaml", path, f"root must be a mapping, got {type(data).__name__}")

    title = _require(data, "title", str, "meta.yaml", "")
    if not title.strip():
        raise SchemaError("meta.yaml", path, "title is empty")

    date = _require(data, "date", str, "meta.yaml", "")
    if len(date) != DATE_RE_LEN or date[4] != "-" or date[7] != "-":
        raise SchemaError("meta.yaml", path, f"date {date!r} must be YYYY-MM-DD")

    language = _require(data, "language", str, "meta.yaml", "")
    if language not in ALLOWED_LANGUAGES:
        raise SchemaError(
            "meta.yaml",
            path,
            f"language {language!r} not in allowed set {sorted(ALLOWED_LANGUAGES)}",
        )

    videos = _require(data, "videos", list, "meta.yaml", "")
    if not videos:
        raise SchemaError("meta.yaml", path, "videos[] must not be empty")

    seen_slugs: set[str] = set()
    for i, video in enumerate(videos):
        v_path = f"videos[{i}]"
        if not isinstance(video, dict):
            raise SchemaError("meta.yaml", path, f"{v_path} is not an object")
        slug = _require(video, "slug", str, "meta.yaml", v_path)
        try:
            validate_video_slug(slug)
        except InvalidWorkflowInput as e:
            raise SchemaError("meta.yaml", path, f"{v_path}.slug: {e}") from None
        if slug in seen_slugs:
            raise SchemaError("meta.yaml", path, f"{v_path}.slug {slug!r} duplicated")
        seen_slugs.add(slug)

        _require(video, "title", str, "meta.yaml", v_path)
        vimeo_url = video.get("vimeo_url", "")
        if vimeo_url:
            try:
                validate_vimeo_url(vimeo_url)
            except InvalidWorkflowInput as e:
                raise SchemaError("meta.yaml", path, f"{v_path}.vimeo_url: {e}") from None

    # The talk_id (directory name) isn't in the file but if the caller passes
    # a repo-relative path we can sanity-check it too.
    if "/talks/" in path or path.startswith("talks/"):
        parts = path.replace("\\", "/").split("/")
        try:
            talk_id = parts[parts.index("talks") + 1]
            validate_talk_id(talk_id)
        except (ValueError, IndexError, InvalidWorkflowInput):
            pass  # non-fatal — not every caller uses the canonical layout

    return data
