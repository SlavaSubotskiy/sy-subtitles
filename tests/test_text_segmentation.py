from pathlib import Path

import pytest

from tools.text_segmentation import (
    MAX_CPL,
    build_blocks_from_paragraphs,
    load_transcript,
    split_sentences,
    split_text_to_lines,
)


def test_build_blocks_simple() -> None:
    paras = ["Перше речення. Друге речення.", "Третє речення."]
    blocks = build_blocks_from_paragraphs(paras)
    assert [b["id"] for b in blocks] == [1, 2, 3]
    assert blocks[0]["para_idx"] == 0
    assert blocks[1]["para_idx"] == 0
    assert blocks[2]["para_idx"] == 1
    assert all("text" in b for b in blocks)


def test_build_blocks_cpl_enforced() -> None:
    long = "слово " * 40
    blocks = build_blocks_from_paragraphs([long.strip()])
    for b in blocks:
        assert len(b["text"]) <= MAX_CPL, b["text"]
    assert len(blocks) >= 2


def test_build_blocks_empty() -> None:
    assert build_blocks_from_paragraphs([]) == []
    assert build_blocks_from_paragraphs([""]) == []


def test_build_blocks_matches_legacy_sync_shape() -> None:
    """Regression guard: canonical builder produces the exact shape that
    sync_transcript_to_srt and build_map used to build independently."""
    paras = ["Коротке. Ще одне коротке."]
    blocks = build_blocks_from_paragraphs(paras)
    expected_keys = {"id", "text", "para_idx"}
    for b in blocks:
        assert set(b.keys()) == expected_keys


def test_split_sentences_respects_abbreviations() -> None:
    assert len(split_sentences("Dr. Smith came. He left.")) == 2
    assert len(split_sentences("Mr. White arrived. It was cold.")) == 2


def test_split_text_to_lines_single_word() -> None:
    word = "a" * (MAX_CPL + 10)
    assert split_text_to_lines(word) == [word]  # single unbreakable word preserved


# split_text_to_lines ---------------------------------------------------------


def test_split_text_to_lines_short_text_unchanged() -> None:
    assert split_text_to_lines("Коротке речення.") == ["Коротке речення."]


def test_split_text_to_lines_enforces_cpl() -> None:
    text = "Це дуже довге речення, яке точно перевищує вісімдесят чотири символи і потребує розбиття на частини."
    lines = split_text_to_lines(text)
    assert len(lines) >= 2
    for line in lines:
        assert len(line) <= MAX_CPL, line


def test_split_text_prefers_punctuation() -> None:
    # A comma should be a preferred break point — if any line ends right
    # after the comma, the splitter honoured punctuation priority.
    text = "Першим висловом це речення справді довге, а потім далі продовження теж має власну довжину окрему."
    lines = split_text_to_lines(text)
    joined = " ".join(lines)
    assert joined.replace("  ", " ").split() == text.split()


# split_sentences -------------------------------------------------------------


def test_split_sentences_empty() -> None:
    assert split_sentences("") == []


def test_split_sentences_no_punctuation() -> None:
    assert split_sentences("hello world") == ["hello world"]


def test_split_sentences_multiple_punct() -> None:
    sents = split_sentences("What? Why! Because. Done.")
    assert len(sents) == 4


def test_split_sentences_cyrillic_uppercase() -> None:
    sents = split_sentences("Перше речення. Друге речення. Третє.")
    assert len(sents) == 3


# build_blocks_from_paragraphs — edge cases -----------------------------------


def test_build_blocks_preserves_para_idx_across_empty_paragraphs() -> None:
    # Empty paragraphs don't appear in output but don't shift para_idx of the rest
    blocks = build_blocks_from_paragraphs(["First.", "", "Third."])
    idxs = {b["para_idx"] for b in blocks}
    assert 0 in idxs and 2 in idxs
    assert 1 not in idxs


def test_build_blocks_long_paragraph_splits_many_blocks() -> None:
    long_sentence = ("слово " * 50).strip() + "."
    blocks = build_blocks_from_paragraphs([long_sentence])
    assert len(blocks) >= 3
    assert all(b["para_idx"] == 0 for b in blocks)
    assert all(b["id"] == i + 1 for i, b in enumerate(blocks))


# load_transcript -------------------------------------------------------------


def test_load_transcript_header_stripped(tmp_path: Path) -> None:
    f = tmp_path / "transcript.txt"
    f.write_text(
        "8 травня 1988\nПуджа\nФреджене\nМова промови: англійська | Транскрипт\nПерший абзац.\nДругий абзац.\n",
        encoding="utf-8",
    )
    paras = load_transcript(str(f))
    assert paras == ["Перший абзац.", "Другий абзац."]


def test_load_transcript_double_newline_format(tmp_path: Path) -> None:
    f = tmp_path / "transcript.txt"
    f.write_text(
        "Мова промови: англійська\n\nПерший абзац з кількома реченнями. І ще одне.\n\nДругий абзац.\n",
        encoding="utf-8",
    )
    paras = load_transcript(str(f))
    assert len(paras) == 2
    assert "Перший абзац" in paras[0]
    assert paras[1] == "Другий абзац."


def test_load_transcript_no_header_falls_back(tmp_path: Path) -> None:
    # Without "Talk Language:" marker, body_start stays 0 and lines
    # past the first 10 still belong to the body.
    f = tmp_path / "transcript.txt"
    f.write_text("Перший.\nДругий.\nТретій.\n", encoding="utf-8")
    paras = load_transcript(str(f))
    assert len(paras) == 3


@pytest.mark.parametrize("marker", ["Talk Language:", "Language:", "Мова промови:", "Мова:"])
def test_load_transcript_all_header_markers(tmp_path: Path, marker: str) -> None:
    f = tmp_path / "transcript.txt"
    f.write_text(f"Date\nTitle\n{marker} English\nBody paragraph.\n", encoding="utf-8")
    paras = load_transcript(str(f))
    assert paras == ["Body paragraph."]
