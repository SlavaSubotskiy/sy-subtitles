"""Tests for tools.optimize_srt."""

import json

from tools.config import OptimizeConfig
from tools.optimize_srt import (
    build_blocks_from_uk_whisper,
    find_best_split_point,
    find_block_split_point,
    merge_short_blocks,
    optimize,
    split_blocks_by_duration,
    split_blocks_by_size,
)

# --- find_best_split_point ---


def test_find_best_split_point_short_text():
    assert find_best_split_point("Short", 42) is None


def test_find_best_split_point_long_text():
    text = "This is a sentence that is quite long. And continues with more words after that."
    pos = find_best_split_point(text, 42)
    assert pos is not None
    assert len(text[:pos]) <= 42
    assert len(text[pos + 1 :]) <= 42


def test_find_best_split_point_prefers_punctuation():
    text = "First sentence ends here and more. Second sentence comes after this."
    pos = find_best_split_point(text, 42)
    assert pos is not None
    # Should split after the period
    assert text[:pos].endswith(".")


# --- find_block_split_point ---


def test_find_block_split_point_sentence_boundary():
    text = "First sentence here. Second sentence there."
    pos = find_block_split_point(text)
    assert pos is not None
    part1 = text[:pos].strip()
    part2 = text[pos:].strip()
    assert part1.endswith(".")
    assert len(part2) > 0


def test_find_block_split_point_clause_boundary():
    text = "One long clause without ending, but another part follows here"
    pos = find_block_split_point(text)
    assert pos is not None
    assert 0 < pos < len(text)


def test_find_block_split_point_word_fallback():
    text = "word1 word2 word3 word4 word5 word6"
    pos = find_block_split_point(text)
    assert pos is not None
    assert 0 < pos < len(text)


# --- split_blocks_by_duration ---


def test_split_blocks_by_duration_under_limit():
    config = OptimizeConfig(max_duration_ms=7000)
    blocks = [{"idx": 1, "start_ms": 0, "end_ms": 5000, "text": "Short block."}]
    result, splits = split_blocks_by_duration(blocks, config)
    assert splits == 0
    assert len(result) == 1


def test_split_blocks_by_duration_over_limit():
    config = OptimizeConfig(max_duration_ms=7000, min_duration_ms=1000)
    text = "First sentence here. Second sentence continues with more words to fill."
    blocks = [{"idx": 1, "start_ms": 0, "end_ms": 15000, "text": text}]
    result, splits = split_blocks_by_duration(blocks, config)
    assert splits > 0
    assert len(result) > 1
    # Text preserved across split
    combined = " ".join(b["text"] for b in result)
    assert combined.replace("  ", " ").strip() == text.strip()


# --- split_blocks_by_size ---


def test_split_blocks_by_size_under_limit():
    config = OptimizeConfig()
    blocks = [{"idx": 1, "start_ms": 0, "end_ms": 5000, "text": "Short text."}]
    result, splits = split_blocks_by_size(blocks, config)
    assert splits == 0
    assert len(result) == 1


def test_split_blocks_by_size_over_limit():
    config = OptimizeConfig(max_chars_block=40)
    text = "This is a very long block of text. It exceeds the character limit by quite a lot."
    blocks = [{"idx": 1, "start_ms": 0, "end_ms": 6000, "text": text}]
    result, splits = split_blocks_by_size(blocks, config)
    assert splits > 0
    assert len(result) > 1


# --- merge_short_blocks ---


def test_merge_short_blocks_merges_two_short():
    config = OptimizeConfig(min_duration_ms=1200)
    blocks = [
        {"idx": 1, "start_ms": 0, "end_ms": 800, "text": "Hi"},
        {"idx": 2, "start_ms": 900, "end_ms": 1700, "text": "there"},
    ]
    result, merged = merge_short_blocks(blocks, config)
    assert merged > 0
    assert len(result) == 1
    assert "Hi" in result[0]["text"]
    assert "there" in result[0]["text"]


def test_merge_short_blocks_keeps_long():
    config = OptimizeConfig(min_duration_ms=1200)
    blocks = [
        {"idx": 1, "start_ms": 0, "end_ms": 3000, "text": "This is long enough to stay."},
        {"idx": 2, "start_ms": 3200, "end_ms": 6200, "text": "And so is this block."},
    ]
    result, merged = merge_short_blocks(blocks, config)
    assert merged == 0
    assert len(result) == 2


# --- build_blocks_from_uk_whisper ---


def test_build_blocks_from_uk_whisper(tmp_path):
    data = {
        "language": "uk",
        "segments": [
            {"id": 0, "start": 1.0, "end": 4.0, "text": "Перший блок."},
            {"id": 1, "start": 4.5, "end": 7.5, "text": "Другий блок."},
            {"id": 2, "start": 8.0, "end": 11.0, "text": ""},
        ],
    }
    path = tmp_path / "uk_whisper.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    blocks = build_blocks_from_uk_whisper(path)
    assert len(blocks) == 2  # empty segment skipped
    assert blocks[0]["text"] == "Перший блок."
    assert blocks[0]["start_ms"] == 1000
    assert blocks[1]["text"] == "Другий блок."


# --- optimize() full pipeline ---


def test_optimize_text_preserved(sample_srt_path, sample_whisper_path, tmp_srt):
    optimize(
        srt_path=str(sample_srt_path),
        json_path=str(sample_whisper_path),
        output_path=str(tmp_srt),
    )
    from tools.srt_utils import parse_srt

    original = parse_srt(sample_srt_path)
    optimized = parse_srt(tmp_srt)
    orig_text = " ".join(b["text"].replace("\n", " ") for b in original)
    opt_text = " ".join(b["text"].replace("\n", " ") for b in optimized)
    # Normalize whitespace for comparison
    import re

    orig_norm = re.sub(r"\s+", " ", orig_text).strip()
    opt_norm = re.sub(r"\s+", " ", opt_text).strip()
    assert orig_norm == opt_norm


def test_optimize_output_written(sample_srt_path, sample_whisper_path, tmp_srt):
    optimize(
        srt_path=str(sample_srt_path),
        json_path=str(sample_whisper_path),
        output_path=str(tmp_srt),
    )
    assert tmp_srt.exists()
    assert tmp_srt.stat().st_size > 0


def test_optimize_with_uk_json(sample_whisper_path, tmp_path):
    uk_data = {
        "language": "uk",
        "segments": [
            {"id": 0, "start": 1.0, "end": 4.0, "text": "Перший блок тексту."},
            {"id": 1, "start": 4.5, "end": 7.5, "text": "Другий блок з текстом."},
        ],
    }
    uk_json = tmp_path / "uk_whisper.json"
    uk_json.write_text(json.dumps(uk_data, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "uk.srt"

    optimize(
        srt_path=None,
        json_path=str(sample_whisper_path),
        output_path=str(output),
        uk_json_path=str(uk_json),
    )
    assert output.exists()
    from tools.srt_utils import parse_srt

    blocks = parse_srt(output)
    full_text = " ".join(b["text"] for b in blocks)
    assert "Перший" in full_text
    assert "Другий" in full_text


def test_optimize_without_whisper_json(sample_srt_path, tmp_srt):
    optimize(
        srt_path=str(sample_srt_path),
        json_path=None,
        output_path=str(tmp_srt),
    )
    assert tmp_srt.exists()
    from tools.srt_utils import parse_srt

    blocks = parse_srt(tmp_srt)
    assert len(blocks) > 0
