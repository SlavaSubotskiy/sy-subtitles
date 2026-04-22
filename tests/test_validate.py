"""Tests for tools.validate_subtitles — header stripping and validation checks."""

import json

import pytest

from tools.config import OptimizeConfig
from tools.validate_subtitles import (
    TimeAnchor,
    _resolve_anchor,
    check_overlaps,
    check_sequential_numbering,
    check_statistics,
    check_text_preservation,
    check_time_range,
    extract_words,
    normalize_text,
    strip_header,
    validate,
)

# ---------------------------------------------------------------------------
#  strip_header
# ---------------------------------------------------------------------------


def test_strip_header_en():
    text = (
        "19 September 1993\n"
        "Ganesha Puja\n"
        "Campus, Cabella Ligure (Italy)\n"
        "Talk Language: English | Transcript (English) – VERIFIED\n"
        "\n"
        "Today we have gathered here."
    )
    assert strip_header(text).strip() == "Today we have gathered here."


def test_strip_header_uk():
    text = "19 вересня 1993\nПуджа Ґанеші\nМова промови: англійська | Транскрипт (українська)\n\nТекст промови."
    assert strip_header(text).strip() == "Текст промови."


def test_strip_header_language_prefix():
    text = "Language: uk\n\nBody text."
    assert strip_header(text).strip() == "Body text."


def test_strip_header_uk_short_marker():
    text = "19 вересня 1993\nПуджа Ґанеші\nМова: англійська\n\nТекст."
    assert strip_header(text).strip() == "Текст."


def test_strip_header_no_header():
    text = "Текст без шапки.\nДругий рядок."
    assert strip_header(text) == text


def test_strip_header_header_beyond_10_lines():
    """If marker appears after line 10, it should NOT be stripped."""
    lines = [f"Line {i}" for i in range(12)]
    lines.append("Talk Language: English")
    lines.append("Body text.")
    text = "\n".join(lines)
    assert strip_header(text) == text


# ---------------------------------------------------------------------------
#  Helpers for building test SRT / transcript files
# ---------------------------------------------------------------------------


def _write_srt(path, blocks):
    """Write a minimal SRT file from a list of (idx, start, end, text) tuples.

    *start* and *end* are SRT timecodes like ``"00:00:01,000"``.
    """
    lines = []
    for idx, start, end, text in blocks:
        lines.append(str(idx))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_transcript(path, text):
    path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
#  normalize_text / extract_words
# ---------------------------------------------------------------------------


def test_normalize_text_collapses_whitespace():
    assert normalize_text("  hello   world\nnew  ") == "hello world new"


def test_extract_words_skips_punctuation():
    words = extract_words("Hello, world! -- test.")
    assert "Hello," in words
    assert "world!" in words
    # pure-punctuation token "--" should be dropped
    assert "--" not in words


# ---------------------------------------------------------------------------
#  CHECK 1: Text preservation
# ---------------------------------------------------------------------------


def test_text_preservation_match(tmp_path):
    """SRT text that exactly matches transcript should pass."""
    srt_file = tmp_path / "uk.srt"
    transcript_file = tmp_path / "transcript.txt"

    _write_srt(
        srt_file,
        [
            (1, "00:00:01,000", "00:00:03,000", "Привіт усім."),
            (2, "00:00:03,500", "00:00:06,000", "Сьогодні ми зібрались тут."),
        ],
    )
    _write_transcript(transcript_file, "Привіт усім. Сьогодні ми зібрались тут.")

    from tools.srt_utils import parse_srt

    blocks = parse_srt(str(srt_file))
    report = []
    result = check_text_preservation(blocks, str(transcript_file), report)
    assert result is True


def test_text_preservation_mismatch(tmp_path):
    """Different words between transcript and SRT should fail."""
    srt_file = tmp_path / "uk.srt"
    transcript_file = tmp_path / "transcript.txt"

    _write_srt(
        srt_file,
        [
            (1, "00:00:01,000", "00:00:03,000", "Привіт усім."),
            (2, "00:00:03,500", "00:00:06,000", "Сьогодні ІНШЕ СЛОВО."),
        ],
    )
    _write_transcript(transcript_file, "Привіт усім. Сьогодні ми зібрались тут.")

    from tools.srt_utils import parse_srt

    blocks = parse_srt(str(srt_file))
    report = []
    result = check_text_preservation(blocks, str(transcript_file), report)
    assert result is False


def test_text_preservation_with_header(tmp_path):
    """Header in transcript should be stripped before comparison."""
    srt_file = tmp_path / "uk.srt"
    transcript_file = tmp_path / "transcript.txt"

    _write_srt(
        srt_file,
        [
            (1, "00:00:01,000", "00:00:04,000", "Текст промови."),
        ],
    )
    _write_transcript(
        transcript_file,
        "19 вересня 1993\nПуджа Ґанеші\nМова: англійська\n\nТекст промови.",
    )

    from tools.srt_utils import parse_srt

    blocks = parse_srt(str(srt_file))
    report = []
    result = check_text_preservation(blocks, str(transcript_file), report)
    assert result is True


def test_text_preservation_ignores_stage_direction_lines(tmp_path):
    """`^\\[…\\]$` editorial lines in the transcript must not cause a mismatch.

    The builder strips them via `load_transcript`; the SRT therefore never
    contains them. Validation must apply the same rule so transcript and
    SRT round-trip cleanly. Regression guard for the `check_text_preservation`
    + `load_transcript` contract.
    """
    srt_file = tmp_path / "uk.srt"
    transcript_file = tmp_path / "transcript.txt"

    _write_srt(
        srt_file,
        [
            (1, "00:00:01,000", "00:00:03,000", "Перший бхаджан заспівано."),
            (2, "00:00:03,500", "00:00:06,000", "Багато людей запитували Мене."),
        ],
    )
    _write_transcript(
        transcript_file,
        "Мова промови: англійська\n\n"
        "[Промова англійською]\n"
        "Перший бхаджан заспівано.\n"
        "[Переклад з маратхі на англійську]\n"
        "Багато людей запитували Мене.\n"
        "[Музика]\n",
    )

    from tools.srt_utils import parse_srt

    blocks = parse_srt(str(srt_file))
    report = []
    assert check_text_preservation(blocks, str(transcript_file), report) is True


# ---------------------------------------------------------------------------
#  CHECK 2: Overlap detection
# ---------------------------------------------------------------------------


def test_no_overlaps():
    """Non-overlapping blocks should pass."""
    blocks = [
        {"idx": 1, "start_ms": 1000, "end_ms": 3000, "text": "A"},
        {"idx": 2, "start_ms": 3100, "end_ms": 5000, "text": "B"},
        {"idx": 3, "start_ms": 5100, "end_ms": 7000, "text": "C"},
    ]
    report = []
    assert check_overlaps(blocks, report) is True


def test_overlap_detected():
    """Overlapping blocks should fail."""
    blocks = [
        {"idx": 1, "start_ms": 1000, "end_ms": 4000, "text": "A"},
        {"idx": 2, "start_ms": 3500, "end_ms": 6000, "text": "B"},
    ]
    report = []
    assert check_overlaps(blocks, report) is False
    report_text = "\n".join(report)
    assert "Overlapping blocks: 1" in report_text


def test_adjacent_blocks_no_overlap():
    """Blocks where end == start of next should NOT count as overlap."""
    blocks = [
        {"idx": 1, "start_ms": 0, "end_ms": 2000, "text": "A"},
        {"idx": 2, "start_ms": 2000, "end_ms": 4000, "text": "B"},
    ]
    report = []
    assert check_overlaps(blocks, report) is True


# ---------------------------------------------------------------------------
#  CHECK 4: Sequential numbering
# ---------------------------------------------------------------------------


def test_sequential_numbering_correct():
    blocks = [
        {"idx": 1, "start_ms": 0, "end_ms": 1000, "text": "A"},
        {"idx": 2, "start_ms": 1100, "end_ms": 2000, "text": "B"},
        {"idx": 3, "start_ms": 2100, "end_ms": 3000, "text": "C"},
    ]
    report = []
    assert check_sequential_numbering(blocks, report) is True


def test_sequential_numbering_wrong():
    blocks = [
        {"idx": 1, "start_ms": 0, "end_ms": 1000, "text": "A"},
        {"idx": 3, "start_ms": 1100, "end_ms": 2000, "text": "B"},
        {"idx": 5, "start_ms": 2100, "end_ms": 3000, "text": "C"},
    ]
    report = []
    assert check_sequential_numbering(blocks, report) is False
    report_text = "\n".join(report)
    assert "Numbering errors: 2" in report_text


def test_sequential_numbering_starting_from_zero():
    """Numbering that starts at 0 instead of 1 should fail."""
    blocks = [
        {"idx": 0, "start_ms": 0, "end_ms": 1000, "text": "A"},
        {"idx": 1, "start_ms": 1100, "end_ms": 2000, "text": "B"},
    ]
    report = []
    assert check_sequential_numbering(blocks, report) is False


# ---------------------------------------------------------------------------
#  CPS / Duration / Gap statistics
# ---------------------------------------------------------------------------


def test_cps_within_limits():
    """Block with low CPS should not trip any CPS counters."""
    blocks = [
        {"idx": 1, "start_ms": 0, "end_ms": 2000, "text": "0123456789"},
    ]
    config = OptimizeConfig()
    report = []
    stats = check_statistics(blocks, config, report)
    assert stats["cps_over_target"] == 0
    assert stats["cps_over_hard"] == 0


def test_cps_exceeds_hard_max():
    """Block with very high CPS should be flagged."""
    text = "A" * 60
    blocks = [
        {"idx": 1, "start_ms": 0, "end_ms": 1000, "text": text},
    ]
    config = OptimizeConfig()
    report = []
    stats = check_statistics(blocks, config, report)
    assert stats["cps_over_target"] == 1
    assert stats["cps_over_hard"] == 1


def test_cps_between_target_and_hard():
    """Block between target (15) and hard max (20) — over target only."""
    # 18 chars in 1 second = 18 CPS
    text = "A" * 18
    blocks = [
        {"idx": 1, "start_ms": 0, "end_ms": 1000, "text": text},
    ]
    config = OptimizeConfig()
    report = []
    stats = check_statistics(blocks, config, report)
    assert stats["cps_over_target"] == 1
    assert stats["cps_over_hard"] == 0


def test_duration_under_min():
    """Block shorter than min_duration_ms (1200) should be flagged."""
    blocks = [
        {"idx": 1, "start_ms": 0, "end_ms": 500, "text": "Ok"},
    ]
    config = OptimizeConfig()
    report = []
    stats = check_statistics(blocks, config, report)
    assert stats["duration_under_min"] == 1


def test_duration_over_max():
    """Block longer than max_duration_ms (21000) should be flagged."""
    blocks = [
        {"idx": 1, "start_ms": 0, "end_ms": 25000, "text": "Long text."},
    ]
    config = OptimizeConfig()
    report = []
    stats = check_statistics(blocks, config, report)
    assert stats["duration_over_max"] == 1


def test_duration_within_limits():
    """Block within min/max duration should pass."""
    blocks = [
        {"idx": 1, "start_ms": 0, "end_ms": 3000, "text": "Normal block."},
    ]
    config = OptimizeConfig()
    report = []
    stats = check_statistics(blocks, config, report)
    assert stats["duration_under_min"] == 0
    assert stats["duration_over_max"] == 0


# ---------------------------------------------------------------------------
#  Gap validation
# ---------------------------------------------------------------------------


def test_gap_under_min():
    """Gap smaller than min_gap_ms (80) should be flagged."""
    blocks = [
        {"idx": 1, "start_ms": 0, "end_ms": 2000, "text": "A"},
        {"idx": 2, "start_ms": 2050, "end_ms": 4000, "text": "B"},
    ]
    config = OptimizeConfig()
    report = []
    stats = check_statistics(blocks, config, report)
    assert stats["gap_under_min"] == 1


def test_gap_sufficient():
    """Gap equal to or above min_gap_ms should pass."""
    blocks = [
        {"idx": 1, "start_ms": 0, "end_ms": 2000, "text": "A"},
        {"idx": 2, "start_ms": 2100, "end_ms": 4000, "text": "B"},
    ]
    config = OptimizeConfig()
    report = []
    stats = check_statistics(blocks, config, report)
    assert stats["gap_under_min"] == 0


def test_gap_exactly_at_min():
    """Gap exactly equal to min_gap_ms should NOT be flagged."""
    blocks = [
        {"idx": 1, "start_ms": 0, "end_ms": 2000, "text": "A"},
        {"idx": 2, "start_ms": 2080, "end_ms": 4000, "text": "B"},
    ]
    config = OptimizeConfig()
    report = []
    stats = check_statistics(blocks, config, report)
    assert stats["gap_under_min"] == 0


# ---------------------------------------------------------------------------
#  Full validation run
# ---------------------------------------------------------------------------


def test_full_validate_pass(tmp_path):
    """A well-formed SRT + transcript should pass all checks."""
    srt_file = tmp_path / "uk.srt"
    transcript_file = tmp_path / "transcript.txt"
    report_file = tmp_path / "report.txt"

    _write_srt(
        srt_file,
        [
            (1, "00:00:01,000", "00:00:04,000", "Hello everyone."),
            (2, "00:00:04,200", "00:00:08,000", "Today we have gathered here."),
            (3, "00:00:08,200", "00:00:12,000", "Thank you for coming."),
        ],
    )
    _write_transcript(
        transcript_file,
        "Hello everyone. Today we have gathered here. Thank you for coming.",
    )

    passed, report = validate(
        str(srt_file),
        str(transcript_file),
        report_path=str(report_file),
    )

    assert passed is True
    assert report_file.exists()
    report_text = "\n".join(report)
    assert "Overall: PASSED" in report_text


def test_full_validate_fail_overlap(tmp_path):
    """Overlapping blocks should cause overall FAIL."""
    srt_file = tmp_path / "uk.srt"
    transcript_file = tmp_path / "transcript.txt"

    _write_srt(
        srt_file,
        [
            (1, "00:00:01,000", "00:00:05,000", "Hello."),
            (2, "00:00:04,000", "00:00:08,000", "World."),
        ],
    )
    _write_transcript(transcript_file, "Hello. World.")

    passed, report = validate(str(srt_file), str(transcript_file))

    assert passed is False
    report_text = "\n".join(report)
    assert "[FAIL] No overlaps" in report_text


def test_full_validate_fail_numbering(tmp_path):
    """Wrong numbering should cause overall FAIL."""
    srt_file = tmp_path / "uk.srt"
    transcript_file = tmp_path / "transcript.txt"

    _write_srt(
        srt_file,
        [
            (1, "00:00:01,000", "00:00:04,000", "Hello."),
            (5, "00:00:04,200", "00:00:08,000", "World."),
        ],
    )
    _write_transcript(transcript_file, "Hello. World.")

    passed, report = validate(str(srt_file), str(transcript_file))

    assert passed is False
    report_text = "\n".join(report)
    assert "[FAIL] Sequential numbering" in report_text


def test_full_validate_fail_text_mismatch(tmp_path):
    """Mismatched transcript text should cause overall FAIL."""
    srt_file = tmp_path / "uk.srt"
    transcript_file = tmp_path / "transcript.txt"

    _write_srt(
        srt_file,
        [
            (1, "00:00:01,000", "00:00:04,000", "Hello everyone."),
        ],
    )
    _write_transcript(transcript_file, "Completely different text.")

    passed, report = validate(str(srt_file), str(transcript_file))

    assert passed is False
    report_text = "\n".join(report)
    assert "[FAIL] Text preservation" in report_text


def test_full_validate_skip_text_check(tmp_path):
    """When skip_text_check=True, text mismatch should not cause FAIL."""
    srt_file = tmp_path / "uk.srt"
    transcript_file = tmp_path / "transcript.txt"

    _write_srt(
        srt_file,
        [
            (1, "00:00:01,000", "00:00:04,000", "Hello."),
        ],
    )
    _write_transcript(transcript_file, "Completely different text.")

    passed, report = validate(
        str(srt_file),
        str(transcript_file),
        skip_text_check=True,
    )

    assert passed is True
    report_text = "\n".join(report)
    assert "text preservation check skipped" in report_text


def test_full_validate_fail_cps(tmp_path):
    """Very high CPS should cause FAIL (when cps check is not skipped)."""
    srt_file = tmp_path / "uk.srt"
    transcript_file = tmp_path / "transcript.txt"

    # 60 chars in 1.2 seconds = 50 CPS, far above hard_max_cps=20
    long_text = "A" * 60
    _write_srt(
        srt_file,
        [
            (1, "00:00:01,000", "00:00:02,200", long_text),
        ],
    )
    _write_transcript(transcript_file, long_text)

    passed, report = validate(str(srt_file), str(transcript_file))

    assert passed is False
    report_text = "\n".join(report)
    assert "[FAIL] CPS" in report_text


def test_full_validate_skip_cps_check(tmp_path):
    """When skip_cps_check=True, high CPS should not cause FAIL."""
    srt_file = tmp_path / "uk.srt"
    transcript_file = tmp_path / "transcript.txt"

    long_text = "A" * 60
    _write_srt(
        srt_file,
        [
            (1, "00:00:01,000", "00:00:02,200", long_text),
        ],
    )
    _write_transcript(transcript_file, long_text)

    passed, report = validate(
        str(srt_file),
        str(transcript_file),
        skip_cps_check=True,
    )

    report_text = "\n".join(report)
    # CPS line should not appear as FAIL in the summary
    assert "[FAIL] CPS" not in report_text


def test_full_validate_fail_duration(tmp_path):
    """Block too short should cause FAIL when duration check is active."""
    srt_file = tmp_path / "uk.srt"
    transcript_file = tmp_path / "transcript.txt"

    # 500ms block — under min_duration_ms=1200
    _write_srt(
        srt_file,
        [
            (1, "00:00:01,000", "00:00:01,500", "Ok."),
        ],
    )
    _write_transcript(transcript_file, "Ok.")

    passed, report = validate(str(srt_file), str(transcript_file))

    assert passed is False
    report_text = "\n".join(report)
    assert "[FAIL] Duration" in report_text


def test_full_validate_skip_duration_check(tmp_path):
    """When skip_duration_check=True, short blocks should not FAIL on duration."""
    srt_file = tmp_path / "uk.srt"
    transcript_file = tmp_path / "transcript.txt"

    _write_srt(
        srt_file,
        [
            (1, "00:00:01,000", "00:00:01,500", "Ok."),
        ],
    )
    _write_transcript(transcript_file, "Ok.")

    passed, report = validate(
        str(srt_file),
        str(transcript_file),
        skip_duration_check=True,
        skip_cps_check=True,
    )

    assert passed is True


def test_full_validate_fail_gap(tmp_path):
    """Gap under min_gap_ms should cause FAIL."""
    srt_file = tmp_path / "uk.srt"
    transcript_file = tmp_path / "transcript.txt"

    # 30ms gap between blocks — under min_gap_ms=80
    _write_srt(
        srt_file,
        [
            (1, "00:00:01,000", "00:00:04,000", "Hello."),
            (2, "00:00:04,030", "00:00:07,000", "World."),
        ],
    )
    _write_transcript(transcript_file, "Hello. World.")

    passed, report = validate(str(srt_file), str(transcript_file))

    assert passed is False
    report_text = "\n".join(report)
    assert "[FAIL] Gap" in report_text


# ---------------------------------------------------------------------------
#  TimeAnchor + _resolve_anchor
# ---------------------------------------------------------------------------


def test_time_anchor_build_accepts_valid_range():
    a = TimeAnchor.build(1000, 5000, "EN SRT")
    assert a.start_ms == 1000 and a.end_ms == 5000 and a.label == "EN SRT"


def test_time_anchor_build_rejects_inverted_range():
    with pytest.raises(ValueError, match="invalid range"):
        TimeAnchor.build(5000, 1000, "whisper")


def test_time_anchor_build_rejects_negative():
    with pytest.raises(ValueError, match="invalid range"):
        TimeAnchor.build(-1, 1000, "EN SRT")


def _write_en_srt(tmp_path, blocks):
    """Write a minimal EN SRT with (start_ms, end_ms, text) tuples."""
    path = tmp_path / "en.srt"
    lines = []
    for i, (s, e, t) in enumerate(blocks, 1):

        def ms(n):
            h, rem = divmod(n, 3_600_000)
            m, rem = divmod(rem, 60_000)
            sec, milli = divmod(rem, 1000)
            return f"{h:02d}:{m:02d}:{sec:02d},{milli:03d}"

        lines.append(f"{i}\n{ms(s)} --> {ms(e)}\n{t}\n")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_resolve_anchor_en_srt_preferred_over_whisper(tmp_path):
    srt = _write_en_srt(tmp_path, [(1000, 2000, "one"), (3000, 4000, "two")])
    whisper = tmp_path / "whisper.json"
    whisper.write_text(json.dumps({"segments": [{"start": 9.0, "end": 10.0, "words": []}]}), encoding="utf-8")

    report = []
    anchor = _resolve_anchor(str(srt), str(whisper), report)
    assert anchor is not None
    assert anchor.label == "EN SRT"
    assert anchor.start_ms == 1000 and anchor.end_ms == 4000


def test_resolve_anchor_whisper_when_no_en_srt(tmp_path):
    whisper = tmp_path / "whisper.json"
    whisper.write_text(
        json.dumps({"segments": [{"start": 1.5, "end": 2.0, "words": []}, {"start": 7.0, "end": 8.25, "words": []}]}),
        encoding="utf-8",
    )
    report = []
    anchor = _resolve_anchor(None, str(whisper), report)
    assert anchor.label == "whisper"
    assert anchor.start_ms == 1500 and anchor.end_ms == 8250


def test_resolve_anchor_none_when_both_missing():
    assert _resolve_anchor(None, None, []) is None


def test_resolve_anchor_raises_on_empty_en_srt(tmp_path):
    empty = tmp_path / "empty.srt"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="0 blocks"):
        _resolve_anchor(str(empty), None, [])


def test_resolve_anchor_raises_on_empty_whisper(tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"segments": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="0 segments"):
        _resolve_anchor(None, str(empty), [])


# ---------------------------------------------------------------------------
#  check_time_range (refactored signature)
# ---------------------------------------------------------------------------


def _block(idx, s, e, t="x"):
    return {"idx": idx, "start_ms": s, "end_ms": e, "text": t}


def test_check_time_range_within_anchor():
    anchor = TimeAnchor.build(1000, 10_000, "EN SRT")
    blocks = [_block(1, 2000, 3000), _block(2, 5000, 7000)]
    report = []
    assert check_time_range(blocks, anchor, report) is True
    assert any("Time range: OK" in line for line in report)


def test_check_time_range_before_anchor_within_tolerance():
    anchor = TimeAnchor.build(10_000, 20_000, "whisper")
    # 4s before anchor start — within 5s tolerance
    blocks = [_block(1, 6_000, 7_000), _block(2, 11_000, 12_000)]
    assert check_time_range(blocks, anchor, []) is True


def test_check_time_range_before_anchor_beyond_tolerance():
    anchor = TimeAnchor.build(10_000, 20_000, "whisper")
    blocks = [_block(1, 100, 1000), _block(2, 15_000, 16_000)]
    report = []
    assert check_time_range(blocks, anchor, report) is False
    assert any("starts" in line and "before whisper" in line for line in report)


def test_check_time_range_after_anchor_beyond_tolerance():
    anchor = TimeAnchor.build(0, 5_000, "EN SRT")
    blocks = [_block(1, 1_000, 2_000), _block(2, 15_000, 20_000)]
    report = []
    assert check_time_range(blocks, anchor, report) is False
    assert any("ends" in line and "after EN SRT" in line for line in report)


def test_check_time_range_label_appears_in_report():
    anchor = TimeAnchor.build(0, 100_000, "EN SRT")
    blocks = [_block(1, 1_000, 99_000)]
    report = []
    check_time_range(blocks, anchor, report)
    assert any("vs EN SRT" in line for line in report)
