from pathlib import Path

import pytest

from tools.uk_map import UkMapError, parse_uk_map, validate_uk_map

GOOD = """\
# header comment
1 | 00:00:01,000 | 00:00:04,200 | Перший блок
2 | 00:00:04,300 | 00:00:07,500 | Другий блок — з тире
3 | 00:00:07,600 | 00:00:10,000 | Текст з | вертикальною рискою
"""


def _write(tmp_path: Path, content: str) -> str:
    p = tmp_path / "uk.map"
    p.write_text(content, encoding="utf-8")
    return str(p)


def test_parse_good(tmp_path: Path) -> None:
    blocks = validate_uk_map(_write(tmp_path, GOOD))
    assert [b.idx for b in blocks] == [1, 2, 3]
    assert blocks[0].text == "Перший блок"
    assert blocks[1].end_ms == 7500
    assert blocks[2].text == "Текст з | вертикальною рискою"


def test_bom_tolerated(tmp_path: Path) -> None:
    p = tmp_path / "uk.map"
    p.write_bytes("\ufeff".encode() + GOOD.encode())
    blocks = validate_uk_map(str(p))
    assert len(blocks) == 3


def test_missing_field_raises(tmp_path: Path) -> None:
    bad = "1 | 00:00:01,000 | 00:00:02,000\n"
    with pytest.raises(UkMapError, match="4 pipe-separated"):
        validate_uk_map(_write(tmp_path, bad))


def test_bad_timecode(tmp_path: Path) -> None:
    bad = "1 | 00:00:aa,000 | 00:00:02,000 | Текст\n"
    with pytest.raises(UkMapError, match="invalid start timecode"):
        validate_uk_map(_write(tmp_path, bad))


def test_end_before_start(tmp_path: Path) -> None:
    bad = "1 | 00:00:05,000 | 00:00:02,000 | Текст\n"
    with pytest.raises(UkMapError, match="start .* >= end"):
        validate_uk_map(_write(tmp_path, bad))


def test_non_sequential_id(tmp_path: Path) -> None:
    bad = "1 | 00:00:01,000 | 00:00:02,000 | А\n3 | 00:00:02,100 | 00:00:03,000 | Б\n"
    with pytest.raises(UkMapError, match="non-sequential"):
        validate_uk_map(_write(tmp_path, bad))


def test_empty_text(tmp_path: Path) -> None:
    bad = "1 | 00:00:01,000 | 00:00:02,000 | \n"
    with pytest.raises(UkMapError, match="empty text"):
        validate_uk_map(_write(tmp_path, bad))


def test_empty_file(tmp_path: Path) -> None:
    with pytest.raises(UkMapError, match="no blocks"):
        validate_uk_map(_write(tmp_path, "# only comments\n\n"))


def test_non_strict_recovers(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    content = "1 | 00:00:01,000 | 00:00:02,000 | Перший\nbad line\n2 | 00:00:02,100 | 00:00:03,000 | Другий\n"
    blocks = parse_uk_map(_write(tmp_path, content), strict=False)
    assert [b.idx for b in blocks] == [1, 2]
    captured = capsys.readouterr().out
    assert "WARNING" in captured
