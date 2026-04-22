"""Tests for tools.resync_srt — word-level re-alignment across timelines."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.resync_srt import _build_anchor_map, _remap, resync
from tools.srt_utils import parse_srt


def _ms(h: int, m: int, s: int, ms: int = 0) -> str:
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _write_srt(path: Path, rows: list[tuple[int, str, str, str]]) -> None:
    lines = []
    for idx, start, end, text in rows:
        lines.append(str(idx))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
#  _build_anchor_map
# ---------------------------------------------------------------------------


def test_anchor_map_identical_content():
    """Two identical EN SRTs produce anchors with no time shift."""
    en = [
        {"idx": 1, "start_ms": 1000, "end_ms": 2000, "text": "hello world"},
        {"idx": 2, "start_ms": 3000, "end_ms": 4000, "text": "second block"},
    ]
    anchors = _build_anchor_map(en, en)
    assert len(anchors) > 0
    # Every primary_ms should equal secondary_ms for identical content
    for p_ms, s_ms in anchors:
        assert p_ms == s_ms


def test_anchor_map_shifted_content():
    """Secondary shifted by 10s — anchors reflect the offset."""
    primary = [
        {"idx": 1, "start_ms": 10_000, "end_ms": 12_000, "text": "hello world"},
    ]
    secondary = [
        {"idx": 1, "start_ms": 20_000, "end_ms": 22_000, "text": "hello world"},
    ]
    anchors = _build_anchor_map(primary, secondary)
    assert len(anchors) == 2  # "hello", "world"
    for p_ms, s_ms in anchors:
        assert s_ms - p_ms == 10_000


def test_anchor_map_no_overlap():
    """Entirely different content produces no anchors."""
    primary = [{"idx": 1, "start_ms": 0, "end_ms": 1000, "text": "aaaa bbbb"}]
    secondary = [{"idx": 1, "start_ms": 0, "end_ms": 1000, "text": "zzzz yyyy"}]
    assert _build_anchor_map(primary, secondary) == []


def test_anchor_map_partial_overlap():
    """Secondary covers a subset of primary's words — anchors exist only for matches."""
    primary = [
        {"idx": 1, "start_ms": 0, "end_ms": 1000, "text": "alpha beta"},
        {"idx": 2, "start_ms": 2000, "end_ms": 3000, "text": "gamma delta"},
    ]
    secondary = [
        {"idx": 1, "start_ms": 500, "end_ms": 1500, "text": "gamma delta"},
    ]
    anchors = _build_anchor_map(primary, secondary)
    assert len(anchors) == 2  # gamma, delta
    # All anchors reference the second primary block
    for p_ms, _ in anchors:
        assert p_ms >= 2000


# ---------------------------------------------------------------------------
#  _remap
# ---------------------------------------------------------------------------


def test_remap_linear_interpolation():
    anchors = [(1000, 5000), (2000, 6000)]
    assert _remap(1500, anchors) == 5500


def test_remap_within_edge_tolerance_extrapolates():
    """Points just outside the anchor range (≤2000ms) extrapolate linearly."""
    anchors = [(1000, 5000), (2000, 6000)]
    # 500ms before first anchor (1000ms): extrapolate using slope 1.0 → 4500
    assert _remap(500, anchors) == 4500
    # 500ms past last anchor (2000ms): extrapolate → 6500
    assert _remap(2500, anchors) == 6500


def test_remap_far_out_of_range_returns_none():
    """Points beyond the edge tolerance (>2000ms) return None."""
    anchors = [(10_000, 50_000), (20_000, 60_000)]
    assert _remap(5_000, anchors) is None  # 5s before first
    assert _remap(25_000, anchors) is None  # 5s after last


def test_remap_exact_anchor():
    anchors = [(1000, 5000), (2000, 6000)]
    assert _remap(1000, anchors) == 5000
    assert _remap(2000, anchors) == 6000


def test_remap_empty_anchors():
    assert _remap(1000, []) is None


# ---------------------------------------------------------------------------
#  resync (end-to-end)
# ---------------------------------------------------------------------------


def test_resync_identical_content_passes_through(tmp_path):
    """When primary and secondary EN SRTs are identical, output should mirror primary UK."""
    primary_en = tmp_path / "p.en.srt"
    secondary_en = tmp_path / "s.en.srt"
    primary_uk = tmp_path / "p.uk.srt"
    output = tmp_path / "s.uk.srt"

    en_rows = [
        (1, _ms(0, 0, 1, 0), _ms(0, 0, 3, 0), "hello world how are you"),
        (2, _ms(0, 0, 4, 0), _ms(0, 0, 6, 0), "good morning my friend"),
    ]
    _write_srt(primary_en, en_rows)
    _write_srt(secondary_en, en_rows)
    _write_srt(
        primary_uk,
        [
            (1, _ms(0, 0, 1, 0), _ms(0, 0, 3, 0), "Привіт світе як справи друже"),
            (2, _ms(0, 0, 4, 0), _ms(0, 0, 6, 0), "Доброго ранку мій друже"),
        ],
    )

    resync(str(primary_uk), str(primary_en), str(secondary_en), str(output))
    out_blocks = parse_srt(str(output))
    assert len(out_blocks) == 2
    # Text preserved
    assert "Привіт" in out_blocks[0]["text"]
    assert "Доброго ранку" in out_blocks[1]["text"]


def test_resync_secondary_subset_drops_outside_blocks(tmp_path):
    """Secondary covers only some primary content — blocks outside are dropped."""
    primary_en = tmp_path / "p.en.srt"
    secondary_en = tmp_path / "s.en.srt"
    primary_uk = tmp_path / "p.uk.srt"
    output = tmp_path / "s.uk.srt"

    _write_srt(
        primary_en,
        [
            (1, _ms(0, 0, 1, 0), _ms(0, 0, 3, 0), "alpha beta gamma delta"),
            (2, _ms(0, 0, 5, 0), _ms(0, 0, 7, 0), "epsilon zeta eta theta"),
            (3, _ms(0, 0, 9, 0), _ms(0, 0, 11, 0), "iota kappa lambda mu"),
        ],
    )
    # Secondary has only the MIDDLE primary block, shifted to t=0
    _write_srt(
        secondary_en,
        [
            (1, _ms(0, 0, 1, 0), _ms(0, 0, 3, 0), "epsilon zeta eta theta"),
        ],
    )
    _write_srt(
        primary_uk,
        [
            (1, _ms(0, 0, 1, 0), _ms(0, 0, 3, 0), "перший блок"),
            (2, _ms(0, 0, 5, 0), _ms(0, 0, 7, 0), "другий блок"),
            (3, _ms(0, 0, 9, 0), _ms(0, 0, 11, 0), "третій блок"),
        ],
    )

    resync(str(primary_uk), str(primary_en), str(secondary_en), str(output))
    out_blocks = parse_srt(str(output))
    # Blocks 1 and 3 were outside aligned range → dropped
    assert len(out_blocks) == 1
    assert "другий" in out_blocks[0]["text"]


def test_resync_no_alignment_exits(tmp_path):
    """Zero text overlap → process exits non-zero."""
    primary_en = tmp_path / "p.en.srt"
    secondary_en = tmp_path / "s.en.srt"
    primary_uk = tmp_path / "p.uk.srt"
    output = tmp_path / "s.uk.srt"

    _write_srt(primary_en, [(1, _ms(0, 0, 1, 0), _ms(0, 0, 3, 0), "aaa bbb ccc ddd")])
    _write_srt(secondary_en, [(1, _ms(0, 0, 1, 0), _ms(0, 0, 3, 0), "zzz yyy xxx www")])
    _write_srt(primary_uk, [(1, _ms(0, 0, 1, 0), _ms(0, 0, 3, 0), "текст")])

    with pytest.raises(SystemExit):
        resync(str(primary_uk), str(primary_en), str(secondary_en), str(output))
