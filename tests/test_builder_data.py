import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.builder_data import (
    _find_words_for_block,
    _format_block,
    _seconds_to_tc,
    cmd_info,
    cmd_query,
    cmd_search,
)

# _seconds_to_tc --------------------------------------------------------------


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0.0, "00:00:00,000"),
        (1.5, "00:00:01,500"),
        (61.25, "00:01:01,250"),
        (3661.123, "01:01:01,123"),
    ],
)
def test_seconds_to_tc(seconds: float, expected: str) -> None:
    assert _seconds_to_tc(seconds) == expected


def test_seconds_to_tc_rounds_half_up() -> None:
    # 0.9995s → 1000ms (banker's rounding picks 1000 for ties-to-even)
    assert _seconds_to_tc(0.9995) == "00:00:01,000"


# _find_words_for_block ------------------------------------------------------


def _seg(start: float, end: float, words: list[tuple[str, float, float]]) -> dict:
    return {
        "start": start,
        "end": end,
        "text": " ".join(w[0] for w in words),
        "words": [{"word": w, "start": s, "end": e} for w, s, e in words],
    }


def test_find_words_overlapping_only() -> None:
    segments = [
        _seg(0, 5, [("Hello", 0.0, 1.0), ("world", 1.0, 2.0)]),
        _seg(5, 10, [("second", 5.0, 6.0), ("block", 6.0, 7.0)]),
    ]
    block = {"idx": 1, "start_ms": 1500, "end_ms": 5500, "text": "middle"}
    words = _find_words_for_block(block, segments)
    word_texts = [w["word"] for w in words]
    assert "world" in word_texts
    assert "second" in word_texts
    assert "Hello" not in word_texts


def test_find_words_skips_far_segments() -> None:
    segments = [
        _seg(0, 2, [("early", 0.0, 2.0)]),
        _seg(100, 102, [("late", 100.0, 102.0)]),
    ]
    block = {"idx": 1, "start_ms": 50000, "end_ms": 55000, "text": "middle"}
    assert _find_words_for_block(block, segments) == []


def test_find_words_tolerates_small_gap() -> None:
    # Segment end 1s before block start is still scanned (1s tolerance)
    segments = [_seg(0, 2, [("near", 1.5, 1.9)])]
    block = {"idx": 1, "start_ms": 1800, "end_ms": 2500, "text": "x"}
    assert any(w["word"] == "near" for w in _find_words_for_block(block, segments))


# _format_block --------------------------------------------------------------


def test_format_block_with_words() -> None:
    segments = [_seg(1, 4, [("Hello", 1.0, 2.0), ("world", 2.5, 3.5)])]
    block = {"idx": 7, "start_ms": 1000, "end_ms": 4000, "text": "Привіт, світе."}
    lines = _format_block(block, segments)
    joined = "\n".join(lines)
    assert "=== #7 ===" in joined
    assert "Text: Привіт, світе." in joined
    assert "Timing: 00:00:01,000 → 00:00:03,500" in joined
    assert "Hello" in joined and "world" in joined
    assert "00:00:01,000→00:00:02,000" in joined


def test_format_block_falls_back_to_en_srt_timing() -> None:
    # No whisper words overlap → fall back to the block's own timecodes.
    segments = [_seg(100, 200, [("far", 100.0, 101.0)])]
    block = {"idx": 3, "start_ms": 5000, "end_ms": 8000, "text": "orphan"}
    lines = _format_block(block, segments)
    joined = "\n".join(lines)
    assert "EN SRT, no whisper words" in joined
    assert "00:00:05,000 → 00:00:08,000" in joined


# CLI subcommands ------------------------------------------------------------


def _write_pair(tmp_path: Path) -> tuple[str, str]:
    srt = tmp_path / "en.srt"
    srt.write_text(
        "\n".join(
            [
                "1",
                "00:00:01,000 --> 00:00:04,000",
                "Hello world.",
                "",
                "2",
                "00:00:05,000 --> 00:00:08,000",
                "Second line here.",
                "",
                "3",
                "00:00:09,000 --> 00:00:12,000",
                "Closing statement.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    whisper = tmp_path / "whisper.json"
    whisper.write_text(
        json.dumps(
            {
                "language": "en",
                "segments": [
                    _seg(1.0, 4.0, [("Hello", 1.0, 2.0), ("world", 2.5, 3.5)]),
                    _seg(5.0, 8.0, [("Second", 5.0, 6.0), ("line", 6.0, 7.0)]),
                    _seg(9.0, 12.0, [("Closing", 9.0, 11.0)]),
                ],
            }
        ),
        encoding="utf-8",
    )
    return str(srt), str(whisper)


def _run(func, **kwargs) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        func(SimpleNamespace(**kwargs))
    return buf.getvalue()


def test_cmd_info(tmp_path: Path) -> None:
    srt, whisper = _write_pair(tmp_path)
    out = _run(cmd_info, en_srt=srt, whisper_json=whisper)
    assert "3 EN blocks" in out
    assert "5 whisper words" in out


def test_cmd_query_range(tmp_path: Path) -> None:
    srt, whisper = _write_pair(tmp_path)
    out = _run(cmd_query, en_srt=srt, whisper_json=whisper, from_block=1, to_block=2)
    assert "#1" in out and "#2" in out
    assert "#3" not in out


def test_cmd_query_default_range(tmp_path: Path) -> None:
    srt, whisper = _write_pair(tmp_path)
    out = _run(cmd_query, en_srt=srt, whisper_json=whisper, from_block=None, to_block=None)
    assert "#1" in out and "#2" in out and "#3" in out


def test_cmd_search_case_insensitive(tmp_path: Path) -> None:
    srt, whisper = _write_pair(tmp_path)
    out = _run(cmd_search, en_srt=srt, whisper_json=whisper, text="CLOSING")
    assert "#3" in out
    assert "#1" not in out


def test_cmd_search_no_match(tmp_path: Path) -> None:
    srt, whisper = _write_pair(tmp_path)
    out = _run(cmd_search, en_srt=srt, whisper_json=whisper, text="nonexistent")
    assert out.strip() == ""
