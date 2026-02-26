"""Tests for tools.text_export."""

from tools.text_export import export, srt_to_text

# --- srt_to_text ---


def test_srt_to_text_single_paragraph():
    blocks = [
        {"idx": 1, "start_ms": 0, "end_ms": 1000, "text": "Hello"},
        {"idx": 2, "start_ms": 1100, "end_ms": 2000, "text": "world"},
    ]
    result = srt_to_text(blocks)
    assert result == "Hello world"


def test_srt_to_text_multiple_paragraphs():
    blocks = [
        {"idx": 1, "start_ms": 0, "end_ms": 1000, "text": "First"},
        {"idx": 2, "start_ms": 1100, "end_ms": 2000, "text": "part"},
        {"idx": 3, "start_ms": 5000, "end_ms": 6000, "text": "Second"},
        {"idx": 4, "start_ms": 6100, "end_ms": 7000, "text": "part"},
    ]
    result = srt_to_text(blocks, pause_threshold_ms=2000)
    assert "\n" in result
    paragraphs = result.split("\n")
    assert len(paragraphs) == 2
    assert paragraphs[0] == "First part"
    assert paragraphs[1] == "Second part"


def test_srt_to_text_double_spacing_false():
    blocks = [
        {"idx": 1, "start_ms": 0, "end_ms": 1000, "text": "A"},
        {"idx": 2, "start_ms": 5000, "end_ms": 6000, "text": "B"},
    ]
    result = srt_to_text(blocks, double_spacing=False)
    assert result == "A\nB"


def test_srt_to_text_double_spacing_true():
    blocks = [
        {"idx": 1, "start_ms": 0, "end_ms": 1000, "text": "A"},
        {"idx": 2, "start_ms": 5000, "end_ms": 6000, "text": "B"},
    ]
    result = srt_to_text(blocks, double_spacing=True)
    assert result == "A\n\nB"


def test_srt_to_text_empty():
    assert srt_to_text([]) == ""


# --- export() ---


def test_export_with_meta(sample_srt_path, tmp_path):
    meta = tmp_path / "meta.yaml"
    meta.write_text("title: Test Talk\ndate: 2024-01-15\nlocation: London\nlanguage: English\n", encoding="utf-8")
    output = tmp_path / "output.txt"
    count = export(str(sample_srt_path), str(output), meta_path=str(meta))
    assert count == 10
    text = output.read_text(encoding="utf-8")
    assert "Test Talk" in text
    assert "London" in text


def test_export_without_meta(sample_srt_path, tmp_path):
    output = tmp_path / "output.txt"
    count = export(str(sample_srt_path), str(output))
    assert count == 10
    text = output.read_text(encoding="utf-8")
    assert "First block" in text
