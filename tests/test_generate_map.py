"""Tests for tools.generate_map."""

from tools.generate_map import (
    _distribute_in_range,
    _distribute_times_proportional,
    assign_blocks_to_paragraphs,
    split_sentences,
    split_text_to_lines,
)
from tools.text_segmentation import _split_once

# ---------------------------------------------------------------------------
# split_sentences
# ---------------------------------------------------------------------------


def test_split_sentences_basic():
    text = "First sentence. Second sentence. Third one."
    result = split_sentences(text)
    assert result == ["First sentence.", "Second sentence.", "Third one."]


def test_split_sentences_question_exclamation():
    text = "Is it true? Yes! Absolutely."
    result = split_sentences(text)
    assert result == ["Is it true?", "Yes!", "Absolutely."]


def test_split_sentences_abbreviation_dr():
    text = "I'm happy that Dr. Warren could explain it."
    result = split_sentences(text)
    assert result == ["I'm happy that Dr. Warren could explain it."]


def test_split_sentences_abbreviation_mr_mrs():
    text = "Mr. Smith and Mrs. Jones arrived. They sat down."
    result = split_sentences(text)
    assert result == ["Mr. Smith and Mrs. Jones arrived.", "They sat down."]


def test_split_sentences_no_uppercase_after_dot():
    text = "This costs 5.5 million dollars total."
    result = split_sentences(text)
    assert result == ["This costs 5.5 million dollars total."]


def test_split_sentences_ukrainian():
    text = "Перше речення. Друге речення. Третє."
    result = split_sentences(text)
    assert result == ["Перше речення.", "Друге речення.", "Третє."]


def test_split_sentences_single():
    text = "Only one sentence here."
    result = split_sentences(text)
    assert result == ["Only one sentence here."]


def test_split_sentences_quotes():
    """Closing quote after period blocks the lookbehind — stays as one sentence."""
    text = 'She said, "Hello." And then left.'
    result = split_sentences(text)
    # Lookbehind sees " not . before the space, so no split
    assert len(result) == 1


# ---------------------------------------------------------------------------
# split_text_to_lines
# ---------------------------------------------------------------------------


def test_split_text_short():
    text = "Short text."
    assert split_text_to_lines(text) == ["Short text."]


def test_split_text_exactly_84():
    text = "x" * 84
    assert split_text_to_lines(text) == [text]


def test_split_text_over_84_splits():
    text = "Це дуже довге речення, яке містить набагато більше ніж вісімдесят чотири символи, і тому повинно бути розділене."
    result = split_text_to_lines(text)
    assert all(len(line) <= 84 for line in result)
    assert len(result) >= 2
    # All words preserved
    assert " ".join(result) == text


def test_split_text_clause_boundary():
    # Should prefer splitting at comma
    text = "Перша частина речення, друга частина речення, яка є досить довгою щоб перевищити ліміт."
    result = split_text_to_lines(text)
    assert all(len(line) <= 84 for line in result)
    # Check split happened at comma
    assert result[0].endswith(",")


def test_split_text_conjunction():
    # "що" is a conjunction — good split point
    text = "Це перша частина довгого тексту що потребує розбиття на менші шматки для субтитрів."
    if len(text) > 84:
        result = split_text_to_lines(text)
        assert all(len(line) <= 84 for line in result)


# ---------------------------------------------------------------------------
# _split_once
# ---------------------------------------------------------------------------


def test_split_once_single_word():
    assert _split_once("word") == ["word"]


def test_split_once_two_words():
    result = _split_once("hello world this is a very long text" * 3)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# assign_blocks_to_paragraphs
# ---------------------------------------------------------------------------


def _make_block(idx, start_ms, end_ms, text):
    return {"idx": idx, "start_ms": start_ms, "end_ms": end_ms, "text": text}


def test_assign_equal_paragraphs_and_blocks():
    """3 paragraphs, 3 blocks — one block per paragraph."""
    paras = ["First paragraph.", "Second paragraph.", "Third paragraph."]
    blocks = [
        _make_block(1, 0, 3000, "First paragraph."),
        _make_block(2, 3000, 6000, "Second paragraph."),
        _make_block(3, 6000, 9000, "Third paragraph."),
    ]
    groups = assign_blocks_to_paragraphs(paras, blocks)
    assert len(groups) == 3
    assert len(groups[0]) == 1
    assert groups[0][0]["idx"] == 1


def test_assign_more_blocks_than_paragraphs():
    """2 paragraphs, 6 blocks — blocks distributed proportionally."""
    paras = ["Short.", "This is a longer paragraph with more words."]
    blocks = [_make_block(i, i * 1000, (i + 1) * 1000, f"Block {i}") for i in range(1, 7)]
    groups = assign_blocks_to_paragraphs(paras, blocks)
    assert len(groups) == 2
    assert sum(len(g) for g in groups) == 6
    # Second paragraph has more words, should get more blocks
    assert len(groups[1]) >= len(groups[0])


def test_assign_single_paragraph():
    """1 paragraph — all blocks in one group."""
    paras = ["All text."]
    blocks = [_make_block(i, i * 1000, (i + 1) * 1000, f"w{i}") for i in range(1, 5)]
    groups = assign_blocks_to_paragraphs(paras, blocks)
    assert len(groups) == 1
    assert len(groups[0]) == 4


def test_assign_empty():
    paras = ["Text."]
    groups = assign_blocks_to_paragraphs(paras, [])
    assert len(groups) == 1
    assert groups[0] == []


# ---------------------------------------------------------------------------
# _distribute_in_range
# ---------------------------------------------------------------------------


def test_distribute_in_range_single():
    result = _distribute_in_range(0, 10000, [50])
    assert result == [(0, 10000)]


def test_distribute_in_range_equal():
    result = _distribute_in_range(0, 10000, [50, 50])
    assert result[0] == (0, 5000)
    assert result[1] == (5000, 10000)


def test_distribute_in_range_proportional():
    result = _distribute_in_range(0, 10000, [25, 75])
    assert result[0] == (0, 2500)
    assert result[1] == (2500, 10000)


# ---------------------------------------------------------------------------
# _distribute_times_proportional
# ---------------------------------------------------------------------------


def test_distribute_times_no_words():
    result = _distribute_times_proportional([], [10, 20])
    assert result == [(0, 0), (0, 0)]


def test_distribute_times_single_part():
    words = [{"start": 1.0, "end": 2.0}, {"start": 2.0, "end": 3.0}]
    result = _distribute_times_proportional(words, [100])
    assert result == [(1000, 3000)]


def test_distribute_times_two_parts():
    words = [
        {"start": 1.0, "end": 1.5},
        {"start": 1.5, "end": 2.0},
        {"start": 2.0, "end": 2.5},
        {"start": 2.5, "end": 3.0},
    ]
    result = _distribute_times_proportional(words, [50, 50])
    assert len(result) == 2
    # First part starts at first word, second part ends at last word
    assert result[0][0] == 1000
    assert result[1][1] == 3000
