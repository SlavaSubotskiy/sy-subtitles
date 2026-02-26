"""Tests for tools.align_uk."""

from tools.align_uk import (
    distribute_text_to_segments,
    group_whisper_by_pauses,
    load_transcript,
    map_paragraphs_to_segments,
    validate_segments,
)

# --- load_transcript ---


def test_load_transcript_en_strips_header(sample_transcript_en_path):
    paragraphs = load_transcript(sample_transcript_en_path)
    assert len(paragraphs) == 5
    # Header lines should be stripped
    assert not any("Talk Language" in p for p in paragraphs)
    assert paragraphs[0].startswith("I bow to all")


def test_load_transcript_uk_double_spaced(sample_transcript_uk_path):
    paragraphs = load_transcript(sample_transcript_uk_path)
    assert len(paragraphs) == 5
    assert paragraphs[0].startswith("Я вклоняюся")


def test_load_transcript_short_first_paragraph(tmp_path):
    path = tmp_path / "short.txt"
    path.write_text("Hi.\n\nSecond paragraph here.\n\nThird one.", encoding="utf-8")
    paragraphs = load_transcript(path)
    assert len(paragraphs) == 3
    assert paragraphs[0] == "Hi."


# --- group_whisper_by_pauses ---


def test_group_whisper_by_pauses_single_group(sample_whisper_segments):
    groups = group_whisper_by_pauses(sample_whisper_segments, 1)
    assert len(groups) == 1
    assert len(groups[0]) == len(sample_whisper_segments)


def test_group_whisper_by_pauses_n_groups(sample_whisper_segments):
    n = 3
    groups = group_whisper_by_pauses(sample_whisper_segments, n)
    assert len(groups) == n
    total_segs = sum(len(g) for g in groups)
    assert total_segs == len(sample_whisper_segments)


def test_group_whisper_by_pauses_more_than_segments():
    segments = [
        {"id": 0, "start": 0, "end": 1},
        {"id": 1, "start": 2, "end": 3},
    ]
    groups = group_whisper_by_pauses(segments, 5)
    # Can't make more groups than segments
    assert len(groups) == 2


# --- map_paragraphs_to_segments ---


def test_map_paragraphs_equal_count(sample_whisper_segments):
    paragraphs = [f"Para {i}" for i in range(len(sample_whisper_segments))]
    mappings = map_paragraphs_to_segments(paragraphs, sample_whisper_segments)
    assert len(mappings) == len(sample_whisper_segments)
    assert all(m["uk_text"] for m in mappings)


def test_map_paragraphs_more_than_segments(sample_whisper_segments):
    paragraphs = [f"Para {i}" for i in range(len(sample_whisper_segments) + 5)]
    mappings = map_paragraphs_to_segments(paragraphs, sample_whisper_segments)
    # Extra paragraphs merged into last mapping
    assert len(mappings) == len(sample_whisper_segments)
    assert "Para" in mappings[-1]["uk_text"]


def test_map_paragraphs_empty():
    assert map_paragraphs_to_segments([], []) == []


# --- distribute_text_to_segments ---


def test_distribute_single_segment():
    mappings = [
        {
            "uk_text": "Весь текст тут.",
            "segments": [{"id": 0, "start": 0, "end": 5, "text": "All text here."}],
            "en_text": "All text here.",
        }
    ]
    result = distribute_text_to_segments(mappings)
    assert len(result) == 1
    assert result[0]["text"] == "Весь текст тут."


def test_distribute_multiple_segments_proportional():
    mappings = [
        {
            "uk_text": "Перше слово друге слово третє слово четверте слово",
            "segments": [
                {"id": 0, "start": 0, "end": 2, "text": "Short"},
                {"id": 1, "start": 2, "end": 5, "text": "A longer segment text"},
            ],
            "en_text": "Short A longer segment text",
        }
    ]
    result = distribute_text_to_segments(mappings)
    assert len(result) == 2
    # Both segments should have text
    assert result[0]["text"]
    assert result[1]["text"]
    # Combined text preserved
    combined = result[0]["text"] + " " + result[1]["text"]
    assert combined == "Перше слово друге слово третє слово четверте слово"


def test_distribute_empty_mapping_skipped():
    mappings = [
        {
            "uk_text": "Text",
            "segments": [],
            "en_text": "",
        }
    ]
    result = distribute_text_to_segments(mappings)
    assert len(result) == 0


# --- validate_segments ---


def test_validate_clean_segments():
    segments = [
        {
            "id": 0,
            "start": 0.0,
            "end": 5.0,
            "text": "Hello world",
            "words": [
                {"start": 0.0, "end": 2.0, "word": "Hello"},
                {"start": 2.0, "end": 5.0, "word": "world"},
            ],
        }
    ]
    warnings = validate_segments(segments)
    assert len(warnings) == 0


def test_validate_out_of_bounds():
    segments = [
        {
            "id": 0,
            "start": 1.0,
            "end": 3.0,
            "text": "Hello",
            "words": [
                {"start": 0.5, "end": 3.0, "word": "Hello"},
            ],
        }
    ]
    warnings = validate_segments(segments)
    assert any("starts before segment" in w for w in warnings)


def test_validate_non_monotonic():
    segments = [
        {
            "id": 0,
            "start": 0.0,
            "end": 5.0,
            "text": "Hello world",
            "words": [
                {"start": 3.0, "end": 4.0, "word": "Hello"},
                {"start": 1.0, "end": 2.0, "word": "world"},
            ],
        }
    ]
    warnings = validate_segments(segments)
    assert any("non-monotonic" in w for w in warnings)
