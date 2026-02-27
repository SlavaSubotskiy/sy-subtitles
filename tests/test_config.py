"""Tests for tools.config."""

from tools.config import OptimizeConfig


def test_default_values():
    c = OptimizeConfig()
    assert c.target_cps == 15.0
    assert c.hard_max_cps == 20.0
    assert c.max_cpl == 84
    assert c.max_lines == 1
    assert c.max_chars_block == 84
    assert c.min_duration_ms == 1200
    assert c.max_duration_ms == 15000
    assert c.min_gap_ms == 80
    assert c.fps == 24
    assert c.single_line is True


def test_custom_overrides():
    c = OptimizeConfig(target_cps=20.0, min_gap_ms=100, single_line=False)
    assert c.target_cps == 20.0
    assert c.min_gap_ms == 100
    assert c.single_line is False
    # Unchanged defaults
    assert c.max_cpl == 84


def test_single_line_default_true():
    assert OptimizeConfig().single_line is True
