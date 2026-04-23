"""Tests for tools.validate_artifacts — timecode validation modes.

Covers the en-srt-mode relaxations added alongside the builder/validator
contract change: in en-srt mode Opus may drop UK blocks without an EN
counterpart, so the timecode artifact is allowed to have skipped IDs up
to a maximum block count, instead of a strict 1..N sequence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.validate_artifacts import _check_timecodes


def _write(path: Path, ids_with_times: list[tuple[int, str, str]]) -> Path:
    path.write_text(
        "\n".join(f"#{i} | {s} | {e}" for i, s, e in ids_with_times),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
#  Whisper-mode contract: strict sequential IDs, exact count
# ---------------------------------------------------------------------------


def test_sequential_ids_ok(tmp_path):
    p = _write(
        tmp_path / "tc.txt",
        [
            (1, "00:00:01,000", "00:00:03,000"),
            (2, "00:00:04,000", "00:00:06,000"),
            (3, "00:00:07,000", "00:00:09,000"),
        ],
    )
    _check_timecodes(str(p), expected_blocks=3)


def test_non_sequential_ids_rejected_by_default(tmp_path):
    p = _write(
        tmp_path / "tc.txt",
        [
            (1, "00:00:01,000", "00:00:03,000"),
            (3, "00:00:04,000", "00:00:06,000"),  # skips #2
        ],
    )
    with pytest.raises(SystemExit):
        _check_timecodes(str(p))


def test_expected_blocks_mismatch_rejected(tmp_path):
    p = _write(
        tmp_path / "tc.txt",
        [
            (1, "00:00:01,000", "00:00:03,000"),
            (2, "00:00:04,000", "00:00:06,000"),
        ],
    )
    with pytest.raises(SystemExit):
        _check_timecodes(str(p), expected_blocks=5)


# ---------------------------------------------------------------------------
#  En-srt-mode contract: ascending IDs may skip, count capped by max
# ---------------------------------------------------------------------------


def test_skipped_ids_accepted_when_allowed(tmp_path):
    p = _write(
        tmp_path / "tc.txt",
        [
            (1, "00:00:01,000", "00:00:03,000"),
            (3, "00:00:04,000", "00:00:06,000"),  # skips #2
            (7, "00:00:07,000", "00:00:09,000"),  # skips #4,5,6
        ],
    )
    _check_timecodes(str(p), allow_skipped_ids=True, max_blocks=7)


def test_skipped_ids_still_must_be_strictly_ascending(tmp_path):
    """`--allow-skipped-ids` relaxes sequential check, not monotonic."""
    p = _write(
        tmp_path / "tc.txt",
        [
            (3, "00:00:01,000", "00:00:03,000"),
            (2, "00:00:04,000", "00:00:06,000"),  # goes backward
        ],
    )
    with pytest.raises(SystemExit):
        _check_timecodes(str(p), allow_skipped_ids=True, max_blocks=10)


def test_duplicate_id_rejected_even_when_skip_allowed(tmp_path):
    p = _write(
        tmp_path / "tc.txt",
        [
            (1, "00:00:01,000", "00:00:03,000"),
            (1, "00:00:04,000", "00:00:06,000"),
        ],
    )
    with pytest.raises(SystemExit):
        _check_timecodes(str(p), allow_skipped_ids=True, max_blocks=10)


def test_max_blocks_enforced(tmp_path):
    p = _write(
        tmp_path / "tc.txt",
        [
            (1, "00:00:01,000", "00:00:03,000"),
            (2, "00:00:04,000", "00:00:06,000"),
            (3, "00:00:07,000", "00:00:09,000"),
            (4, "00:00:10,000", "00:00:12,000"),
        ],
    )
    # OK: under max
    _check_timecodes(str(p), allow_skipped_ids=True, max_blocks=5)
    # Fail: over max
    with pytest.raises(SystemExit):
        _check_timecodes(str(p), allow_skipped_ids=True, max_blocks=3)
