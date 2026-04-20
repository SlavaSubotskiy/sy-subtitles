"""Tests for tools.build_srt (internal timing passes)."""

from tools.build_srt import (
    apply_padding,
    balance_cps,
    enforce_duration,
    enforce_gaps,
)
from tools.config import OptimizeConfig


def _make_block(idx, start_ms, end_ms, text):
    return {"idx": idx, "start_ms": start_ms, "end_ms": end_ms, "text": text}


# ---------------------------------------------------------------------------
# enforce_gaps
# ---------------------------------------------------------------------------


def test_enforce_gaps_already_ok():
    blocks = [
        _make_block(1, 0, 2000, "A"),
        _make_block(2, 2200, 4000, "B"),
    ]
    config = OptimizeConfig(min_gap_ms=80)
    result = enforce_gaps(blocks, config)
    assert result[0]["end_ms"] == 2000
    assert result[1]["start_ms"] == 2200


def test_enforce_gaps_shrinks_previous():
    blocks = [
        _make_block(1, 0, 2050, "A"),
        _make_block(2, 2060, 4000, "B"),  # gap only 10ms
    ]
    config = OptimizeConfig(min_gap_ms=80)
    result = enforce_gaps(blocks, config)
    assert result[0]["end_ms"] == 2060 - 80  # shrunk to create 80ms gap


# ---------------------------------------------------------------------------
# apply_padding
# ---------------------------------------------------------------------------


def test_apply_padding_extends_into_silence():
    blocks = [
        _make_block(1, 0, 1000, "A"),
        _make_block(2, 5000, 6000, "B"),  # 4s gap
    ]
    config = OptimizeConfig(min_gap_ms=80)
    result = apply_padding(blocks, config)
    # Block 1 should extend into the gap
    assert result[0]["end_ms"] > 1000
    assert result[0]["end_ms"] < 5000


def test_apply_padding_respects_max_duration():
    blocks = [
        _make_block(1, 0, 1000, "A"),
        _make_block(2, 50000, 51000, "B"),  # huge gap
    ]
    config = OptimizeConfig(min_gap_ms=80, max_duration_ms=21000)
    result = apply_padding(blocks, config)
    # Should not exceed max_duration
    assert result[0]["end_ms"] - result[0]["start_ms"] <= 21000


# ---------------------------------------------------------------------------
# enforce_duration
# ---------------------------------------------------------------------------


def test_enforce_duration_extends_short_block():
    blocks = [
        _make_block(1, 0, 500, "Short"),  # only 500ms
        _make_block(2, 5000, 8000, "Normal"),
    ]
    config = OptimizeConfig(min_duration_ms=1200)
    result = enforce_duration(blocks, config)
    dur = result[0]["end_ms"] - result[0]["start_ms"]
    assert dur >= 1200


# ---------------------------------------------------------------------------
# balance_cps
# ---------------------------------------------------------------------------


def test_balance_cps_extends_high_cps_block():
    # 40 chars in 1s = 40 CPS (way over 20 threshold)
    blocks = [
        _make_block(1, 0, 1000, "x" * 40),
        _make_block(2, 10000, 15000, "Normal text."),  # big gap before
    ]
    config = OptimizeConfig()
    result = balance_cps(blocks, config, threshold=20)
    # Block 1 should have been extended
    dur = result[0]["end_ms"] - result[0]["start_ms"]
    assert dur > 1000
