from pathlib import Path

import pytest
import yaml

from tools.glossary_check import (
    STOPWORDS,
    extract_candidates,
    generate_report,
    load_glossary_terms,
)


def _write_glossary(tmp_path: Path, entries: list[dict]) -> str:
    p = tmp_path / "terms.yaml"
    p.write_text(yaml.safe_dump(entries, allow_unicode=True), encoding="utf-8")
    return str(p)


# load_glossary_terms ---------------------------------------------------------


def test_load_glossary_basic(tmp_path: Path) -> None:
    path = _write_glossary(
        tmp_path,
        [
            {"en": "Sahasrara", "uk": "Сахасрара"},
            {"en": "Kundalini", "uk": "Кундаліні"},
        ],
    )
    terms = load_glossary_terms(path)
    assert "sahasrara" in terms
    assert "kundalini" in terms


def test_load_glossary_splits_variants(tmp_path: Path) -> None:
    path = _write_glossary(
        tmp_path,
        [{"en": "Shri Ganesha / Ganapati", "uk": "Шрі Ганеша / Ганапаті"}],
    )
    terms = load_glossary_terms(path)
    assert "shri ganesha" in terms
    assert "ganapati" in terms
    # Individual words from multi-word term are also indexed
    assert "shri" in terms
    assert "ganesha" in terms


def test_load_glossary_empty(tmp_path: Path) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    assert load_glossary_terms(str(path)) == set()


def test_load_glossary_skips_blank(tmp_path: Path) -> None:
    path = _write_glossary(
        tmp_path,
        [{"en": "", "uk": "empty"}, {"en": "Real", "uk": "справжній"}],
    )
    terms = load_glossary_terms(path)
    assert "real" in terms
    assert "" not in terms


# extract_candidates ----------------------------------------------------------


def test_extract_finds_repeated_capitalized() -> None:
    text = "Today we discuss Sahasrara. Let us understand Sahasrara better. The Sahasrara is the final centre."
    cands = extract_candidates(text, known_terms=set())
    assert "Sahasrara" in cands
    assert cands["Sahasrara"] >= 2


def test_extract_skips_sentence_starts() -> None:
    # "Sahasrara" only appears at sentence start → not counted as a candidate.
    text = "Sahasrara. Sahasrara. Sahasrara."
    cands = extract_candidates(text, known_terms=set())
    assert "Sahasrara" not in cands


def test_extract_skips_single_occurrence() -> None:
    text = "We discussed Sahasrara only once today. Then we moved on to other topics entirely."
    cands = extract_candidates(text, known_terms=set())
    assert "Sahasrara" not in cands


def test_extract_skips_stopwords() -> None:
    text = "In this talk today we begin. In this room we are. In this way we proceed."
    cands = extract_candidates(text, known_terms=set())
    for sw in ("In", "This", "We"):
        assert sw not in cands


def test_extract_ignores_known_terms() -> None:
    text = "We speak of Kundalini. The Kundalini awakens. Our Kundalini rises."
    cands = extract_candidates(text, known_terms={"kundalini"})
    assert "Kundalini" not in cands


def test_extract_captures_bigrams() -> None:
    text = "Then Shri Ganesha appeared. We bow to Shri Ganesha. In truth, Shri Ganesha is innocent."
    cands = extract_candidates(text, known_terms=set())
    assert "Shri Ganesha" in cands


def test_extract_filters_short_words() -> None:
    text = "See AB once. See AB twice."
    cands = extract_candidates(text, known_terms=set())
    assert "AB" not in cands


def test_extract_strips_punctuation() -> None:
    text = "We met Mataji. We honour Mataji! We learn from Mataji."
    cands = extract_candidates(text, known_terms=set())
    assert "Mataji" in cands


def test_stopwords_nonempty() -> None:
    assert "the" in STOPWORDS
    assert len(STOPWORDS) > 20


# generate_report -------------------------------------------------------------


def test_generate_report_empty() -> None:
    out = generate_report("1988-Sahasrara", {})
    assert "1988-Sahasrara" in out
    assert "No new candidate terms found" in out


def test_generate_report_sorted_by_count() -> None:
    out = generate_report("talk", {"Alpha": 2, "Beta": 5, "Gamma": 3})
    lines = out.splitlines()
    beta_i = next(i for i, line in enumerate(lines) if "Beta" in line)
    gamma_i = next(i for i, line in enumerate(lines) if "Gamma" in line)
    alpha_i = next(i for i, line in enumerate(lines) if "Alpha" in line)
    assert beta_i < gamma_i < alpha_i


def test_generate_report_includes_counts() -> None:
    out = generate_report("talk", {"Foo": 7})
    assert "7 occurrences" in out
    assert "Found 1 terms" in out


@pytest.mark.parametrize("text", ["", "    \n\n  "])
def test_extract_empty_text_returns_empty(text: str) -> None:
    assert extract_candidates(text, known_terms=set()) == {}
