import json
from pathlib import Path

import pytest
import yaml

from tools.schemas import SchemaError, validate_meta_yaml, validate_whisper_json

GOOD_WHISPER = {
    "language": "en",
    "segments": [
        {
            "id": 0,
            "start": 0.0,
            "end": 2.5,
            "text": "Hello world.",
            "words": [
                {"start": 0.0, "end": 0.5, "word": "Hello"},
                {"start": 0.6, "end": 2.0, "word": "world"},
            ],
        },
        {
            "id": 1,
            "start": 2.6,
            "end": 4.0,
            "text": "Second.",
            "words": [{"start": 2.6, "end": 3.9, "word": "Second"}],
        },
    ],
}

GOOD_META = {
    "title": "Sahasrara Puja",
    "date": "1988-05-08",
    "location": "Fregene, Italy",
    "language": "en",
    "videos": [
        {
            "slug": "Sahasrara-Puja-Talk",
            "title": "Sahasrara Puja Talk",
            "vimeo_url": "https://vimeo.com/88509806/2453ea7524",
        },
    ],
}


def _w(tmp_path: Path, name: str, data) -> str:
    p = tmp_path / name
    if name.endswith(".json"):
        p.write_text(json.dumps(data), encoding="utf-8")
    else:
        p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return str(p)


# whisper.json ---------------------------------------------------------------


def test_whisper_good(tmp_path: Path) -> None:
    validate_whisper_json(_w(tmp_path, "whisper.json", GOOD_WHISPER))


def test_whisper_missing_segments(tmp_path: Path) -> None:
    bad = {"language": "en"}
    with pytest.raises(SchemaError, match="missing required field 'segments'"):
        validate_whisper_json(_w(tmp_path, "whisper.json", bad))


def test_whisper_empty_segments(tmp_path: Path) -> None:
    bad = {"language": "en", "segments": []}
    with pytest.raises(SchemaError, match="empty"):
        validate_whisper_json(_w(tmp_path, "whisper.json", bad))


def test_whisper_end_before_start(tmp_path: Path) -> None:
    bad = {
        "language": "en",
        "segments": [{"start": 5.0, "end": 2.0, "text": "x"}],
    }
    with pytest.raises(SchemaError, match="end .* < start"):
        validate_whisper_json(_w(tmp_path, "whisper.json", bad))


def test_whisper_catastrophic_backward_jump(tmp_path: Path) -> None:
    """Small overlaps are legal (whisper VAD); a >20s rewind is corruption."""
    bad = {
        "language": "en",
        "segments": [
            {"start": 100.0, "end": 120.0, "text": "a"},
            {"start": 3.0, "end": 4.0, "text": "b"},
        ],
    }
    with pytest.raises(SchemaError, match="backward jump > 20s"):
        validate_whisper_json(_w(tmp_path, "whisper.json", bad))


def test_whisper_small_overlap_accepted(tmp_path: Path) -> None:
    """Whisper legitimately produces 1–5s overlaps between consecutive segments."""
    ok = {
        "language": "en",
        "segments": [
            {"start": 10.0, "end": 15.0, "text": "a"},
            {"start": 12.0, "end": 18.0, "text": "b"},
        ],
    }
    validate_whisper_json(_w(tmp_path, "whisper.json", ok))


def test_whisper_bad_json(tmp_path: Path) -> None:
    p = tmp_path / "whisper.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(SchemaError, match="cannot read/parse"):
        validate_whisper_json(str(p))


# meta.yaml ------------------------------------------------------------------


def test_meta_good(tmp_path: Path) -> None:
    validate_meta_yaml(_w(tmp_path, "meta.yaml", GOOD_META))


def test_meta_bad_date(tmp_path: Path) -> None:
    bad = dict(GOOD_META, date="1988/05/08")
    with pytest.raises(SchemaError, match="YYYY-MM-DD"):
        validate_meta_yaml(_w(tmp_path, "meta.yaml", bad))


def test_meta_unknown_language(tmp_path: Path) -> None:
    bad = dict(GOOD_META, language="klingon")
    with pytest.raises(SchemaError, match="language"):
        validate_meta_yaml(_w(tmp_path, "meta.yaml", bad))


def test_meta_empty_videos(tmp_path: Path) -> None:
    bad = dict(GOOD_META, videos=[])
    with pytest.raises(SchemaError, match="videos.* empty"):
        validate_meta_yaml(_w(tmp_path, "meta.yaml", bad))


def test_meta_duplicate_slug(tmp_path: Path) -> None:
    bad = dict(
        GOOD_META,
        videos=[GOOD_META["videos"][0], GOOD_META["videos"][0]],
    )
    with pytest.raises(SchemaError, match="duplicated"):
        validate_meta_yaml(_w(tmp_path, "meta.yaml", bad))


def test_meta_injection_slug_rejected(tmp_path: Path) -> None:
    bad = dict(
        GOOD_META,
        videos=[{"slug": "x;$(curl evil)", "title": "t", "vimeo_url": ""}],
    )
    with pytest.raises(SchemaError, match="invalid video slug"):
        validate_meta_yaml(_w(tmp_path, "meta.yaml", bad))


def test_meta_bad_vimeo_url(tmp_path: Path) -> None:
    bad = dict(
        GOOD_META,
        videos=[
            {
                "slug": "x",
                "title": "t",
                "vimeo_url": "https://evil.com/#vimeo.com/1",
            }
        ],
    )
    with pytest.raises(SchemaError, match="invalid vimeo_url"):
        validate_meta_yaml(_w(tmp_path, "meta.yaml", bad))


# regression against real repo -----------------------------------------------


REPO_META = Path(__file__).resolve().parent.parent / "talks"


@pytest.mark.skipif(not REPO_META.is_dir(), reason="no talks directory")
def test_all_shipped_meta_yaml_valid() -> None:
    """Every meta.yaml in the repo must already pass the schema."""
    failures: list[str] = []
    for meta in sorted(REPO_META.glob("*/meta.yaml")):
        try:
            validate_meta_yaml(str(meta))
        except SchemaError as e:
            failures.append(str(e))
    assert not failures, "Shipped meta.yaml failures:\n" + "\n".join(failures)


@pytest.mark.skipif(not REPO_META.is_dir(), reason="no talks directory")
def test_all_shipped_whisper_valid() -> None:
    failures: list[str] = []
    for w in sorted(REPO_META.glob("*/*/source/whisper.json")):
        try:
            validate_whisper_json(str(w))
        except SchemaError as e:
            failures.append(str(e))
    assert not failures, "Shipped whisper.json failures:\n" + "\n".join(failures[:5])
