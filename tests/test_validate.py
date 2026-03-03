"""Tests for tools.validate_subtitles — header stripping."""

from tools.validate_subtitles import strip_header


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
