from tools.text_segmentation import (
    MAX_CPL,
    build_blocks_from_paragraphs,
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
