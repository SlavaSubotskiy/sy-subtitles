"""Tests for tools.srt_utils."""

from tools.srt_utils import (
    calc_stats,
    load_whisper_json,
    ms_to_time,
    parse_srt,
    time_to_ms,
    write_srt,
)

# --- time_to_ms ---


def test_time_to_ms_normal():
    assert time_to_ms("01:02:03,456") == 3723456


def test_time_to_ms_zero():
    assert time_to_ms("00:00:00,000") == 0


def test_time_to_ms_large():
    assert time_to_ms("99:59:59,999") == 359999999


# --- ms_to_time ---


def test_ms_to_time_roundtrip():
    for ms in [0, 1000, 3723456, 359999999]:
        assert time_to_ms(ms_to_time(ms)) == ms


def test_ms_to_time_format():
    assert ms_to_time(3723456) == "01:02:03,456"


# --- parse_srt ---


def test_parse_srt_valid(sample_srt_path):
    blocks = parse_srt(sample_srt_path)
    assert len(blocks) == 10
    assert blocks[0]["idx"] == 1
    assert blocks[0]["text"] == "First block of text."
    assert blocks[0]["start_ms"] == 1000
    assert blocks[0]["end_ms"] == 4000


def test_parse_srt_utf8_bom(tmp_path):
    srt = tmp_path / "bom.srt"
    content = "\ufeff1\n00:00:01,000 --> 00:00:02,000\nHello\n\n"
    srt.write_text(content, encoding="utf-8")
    blocks = parse_srt(srt)
    assert len(blocks) == 1
    assert blocks[0]["text"] == "Hello"


def test_parse_srt_malformed_skipped(tmp_path):
    srt = tmp_path / "bad.srt"
    content = (
        "1\n00:00:01,000 --> 00:00:02,000\nGood\n\n"
        "bad\nno timecode\ntext\n\n"
        "3\n00:00:03,000 --> 00:00:04,000\nAlso good\n\n"
    )
    srt.write_text(content, encoding="utf-8")
    blocks = parse_srt(srt)
    assert len(blocks) == 2
    assert blocks[0]["text"] == "Good"
    assert blocks[1]["text"] == "Also good"


# --- write_srt ---


def test_write_srt_roundtrip(sample_srt_path, tmp_srt):
    blocks = parse_srt(sample_srt_path)
    write_srt(blocks, tmp_srt)
    reloaded = parse_srt(tmp_srt)
    assert len(reloaded) == len(blocks)
    for orig, new in zip(blocks, reloaded, strict=True):
        assert orig["start_ms"] == new["start_ms"]
        assert orig["end_ms"] == new["end_ms"]
        assert orig["text"] == new["text"]


# --- load_whisper_json ---


def test_load_whisper_json(sample_whisper_path):
    segments = load_whisper_json(sample_whisper_path)
    assert len(segments) == 10
    assert segments[0]["start"] == 1.0
    assert segments[0]["end"] == 4.0


def test_load_whisper_json_has_words(sample_whisper_path):
    segments = load_whisper_json(sample_whisper_path)
    assert "words" in segments[0]
    assert len(segments[0]["words"]) > 0
    assert "start" in segments[0]["words"][0]
    assert "word" in segments[0]["words"][0]


# --- calc_stats ---


def test_calc_stats_counts(sample_blocks, default_config):
    stats = calc_stats(sample_blocks, default_config)
    assert stats["total_blocks"] == 10
    assert stats["overlaps"] == 0
    assert isinstance(stats["avg_cps"], float)
    assert isinstance(stats["max_cps"], float)


def test_calc_stats_known_values(default_config):
    blocks = [
        {"idx": 1, "start_ms": 0, "end_ms": 2000, "text": "Hello world"},
        {"idx": 2, "start_ms": 2100, "end_ms": 4100, "text": "Second line"},
    ]
    stats = calc_stats(blocks, default_config)
    assert stats["total_blocks"] == 2
    assert stats["overlaps"] == 0
    # "Hello world" = 11 chars, 2s => CPS = 5.5
    assert abs(stats["cps_values"][0] - 5.5) < 0.01
    assert stats["gaps"] == [100]


def test_calc_stats_overlap_detected(default_config):
    blocks = [
        {"idx": 1, "start_ms": 0, "end_ms": 3000, "text": "Block one"},
        {"idx": 2, "start_ms": 2500, "end_ms": 5000, "text": "Block two"},
    ]
    stats = calc_stats(blocks, default_config)
    assert stats["overlaps"] == 1


def test_calc_stats_empty():
    stats = calc_stats([])
    assert stats["total_blocks"] == 0
    assert stats["avg_cps"] == 0
    assert stats["max_cps"] == 0
