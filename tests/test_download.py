"""Tests for tools.download — extract_transcript method."""

from bs4 import BeautifulSoup

from tools.download import AmrutaDownloader


def _make_soup(body_html):
    """Wrap HTML in a minimal page with entry-content div."""
    html = f'<html><body><div class="entry-content">{body_html}</div></body></html>'
    return BeautifulSoup(html, "html.parser")


def _extract(body_html):
    dl = AmrutaDownloader.__new__(AmrutaDownloader)
    soup = _make_soup(body_html)
    return dl.extract_transcript(soup)


# --- inline tags ---


def test_inline_em_preserved():
    """<em> inside <p> should NOT create a line break."""
    html = "<p>the electromagnetic force and also <em>pranava</em>: that is</p>"
    result = _extract(html)
    assert result == "the electromagnetic force and also pranava: that is"


def test_inline_strong_preserved():
    html = "<p>This is <strong>very</strong> important.</p>"
    result = _extract(html)
    assert result == "This is very important."


def test_inline_nested_tags():
    html = "<p>Word <em><strong>bold italic</strong></em> end.</p>"
    result = _extract(html)
    assert result == "Word bold italic end."


def test_inline_anchor_preserved():
    html = '<p>Visit <a href="http://example.com">this link</a> please.</p>'
    result = _extract(html)
    assert result == "Visit this link please."


def test_inline_span_preserved():
    html = '<p>Some <span class="highlight">highlighted</span> text.</p>'
    result = _extract(html)
    assert result == "Some highlighted text."


# --- <br> handling ---


def test_br_creates_newline():
    """<br> inside a block element should produce a line break."""
    html = "<h4>19 September 1993<br/>Ganesha Puja<br/>Cabella (Italy)</h4>"
    result = _extract(html)
    assert result == "19 September 1993\nGanesha Puja\nCabella (Italy)"


def test_br_mixed_with_inline():
    html = "<p>Line one with <em>emphasis</em><br/>Line two</p>"
    result = _extract(html)
    assert result == "Line one with emphasis\nLine two"


# --- multiple paragraphs ---


def test_multiple_paragraphs():
    html = "<p>First paragraph.</p><p>Second paragraph.</p>"
    result = _extract(html)
    assert result == "First paragraph.\nSecond paragraph."


def test_heading_separated_from_body():
    """Blank line between heading and first paragraph."""
    html = "<h4>Title</h4><p>Body text.</p>"
    result = _extract(html)
    assert result == "Title\n\nBody text."


def test_consecutive_headings_no_blank_line():
    """No blank line between consecutive headings."""
    html = "<h3>Main</h3><h4>Sub</h4><p>Body.</p>"
    result = _extract(html)
    assert result == "Main\nSub\n\nBody."


def test_amruta_header_format():
    """Full amruta.org header with <br> + paragraph body."""
    html = (
        '<h4 class="wp-block-heading post">'
        "19 September 1993<br/>Ganesha Puja<br/>Cabella (Italy)<br/>"
        "Talk Language: English | Transcript (English) – VERIFIED</h4>"
        '<p class="wp-block-paragraph">Today we have gathered here.</p>'
    )
    result = _extract(html)
    lines = result.split("\n")
    assert lines[0] == "19 September 1993"
    assert lines[3] == "Talk Language: English | Transcript (English) – VERIFIED"
    assert lines[4] == ""  # blank separator
    assert lines[5] == "Today we have gathered here."


# --- noise removal ---


def test_script_and_style_removed():
    html = "<script>alert(1)</script><style>.x{}</style><p>Clean text.</p>"
    result = _extract(html)
    assert result == "Clean text."


def test_embedded_video_removed():
    html = '<div class="embedded-video-wrapper"><iframe src="x"></iframe></div><p>Transcript starts here.</p>'
    result = _extract(html)
    assert result == "Transcript starts here."


def test_iframe_removed():
    html = '<p class="audios"><iframe src="soundcloud"></iframe></p><p>Text.</p>'
    result = _extract(html)
    assert result == "Text."


# --- edge cases ---


def test_empty_content_returns_none():
    html = '<div class="embedded-video-wrapper">video</div>'
    result = _extract(html)
    assert result is None


def test_whitespace_collapsed():
    html = "<p>Too   many    spaces   here.</p>"
    result = _extract(html)
    assert result == "Too many spaces here."


def test_list_items():
    html = "<ul><li>First item</li><li>Second item</li></ul>"
    result = _extract(html)
    assert result == "First item\nSecond item"
