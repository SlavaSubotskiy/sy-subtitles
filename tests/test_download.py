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


# --- deduplication ---


def test_deduplicate_removes_block_of_duplicates():
    """10 consecutive duplicate paragraphs should be removed."""
    html = "".join(f"<p>Paragraph {i}.</p>" for i in range(1, 11))
    # Append same 10 paragraphs again (duplicate block)
    html += "".join(f"<p>Paragraph {i}.</p>" for i in range(1, 11))
    html += "<p>Final paragraph.</p>"
    result = _extract(html)
    lines = result.split("\n")
    assert len(lines) == 11  # 10 unique + 1 final
    assert lines[-1] == "Final paragraph."


def test_deduplicate_keeps_short_repeats():
    """1-2 repeated paragraphs should NOT be removed (could be legitimate)."""
    html = "<p>Repeated line.</p><p>Other text.</p><p>Repeated line.</p>"
    result = _extract(html)
    lines = result.split("\n")
    assert lines.count("Repeated line.") == 2


def test_deduplicate_no_duplicates():
    """All unique paragraphs — nothing removed."""
    html = "<p>One.</p><p>Two.</p><p>Three.</p>"
    result = _extract(html)
    assert result == "One.\nTwo.\nThree."


def test_deduplicate_block_in_middle():
    """Duplicate block in the middle of content."""
    before = "".join(f"<p>Before {i}.</p>" for i in range(5))
    block = "".join(f"<p>Block {i}.</p>" for i in range(4))
    after = "".join(f"<p>After {i}.</p>" for i in range(3))
    html = before + block + after + block  # duplicate block at end
    result = _extract(html)
    lines = result.split("\n")
    # 5 + 4 + 3 = 12 unique, duplicate block of 4 removed
    assert len(lines) == 12


# --- slug uniqueness ---


def _find_videos(body_html):
    dl = AmrutaDownloader.__new__(AmrutaDownloader)
    soup = _make_soup(body_html)
    return dl.extract_video_labels(soup)


def _make_video_wrapper(vimeo_id, title):
    """Create HTML for a video with video-meta-info label."""
    return (
        '<div class="embedded-video-wrapper">'
        f'<iframe src="https://player.vimeo.com/video/{vimeo_id}?h=abc"></iframe>'
        f'<div class="video-meta-info">2001-01-01 {title}, Location, Source, 60′</div>'
        "</div>"
    )


def test_extract_videos_basic():
    """Strategy 1: two different videos with meta-info labels."""
    html = _make_video_wrapper(111, "Krishna Puja") + _make_video_wrapper(222, "Krishna Puja Talk")
    videos = _find_videos(html)
    assert len(videos) == 2
    assert videos[0]["slug"] == "Krishna-Puja"
    assert videos[0]["title"] == "Krishna Puja"
    assert "111" in videos[0]["vimeo_url"]
    assert videos[1]["slug"] == "Krishna-Puja-Talk"
    assert videos[1]["title"] == "Krishna Puja Talk"


def test_extract_videos_fallback_strategy():
    """Strategy 2: plain iframes without wrappers, gets Video-N slugs."""
    html = (
        '<h3>First video</h3><iframe src="https://player.vimeo.com/video/111?h=abc"></iframe>'
        '<h3>Second video</h3><iframe src="https://player.vimeo.com/video/222?h=def"></iframe>'
    )
    videos = _find_videos(html)
    assert len(videos) == 2
    # Strategy 2 uses preceding label or Video-N
    assert all("vimeo_url" in v for v in videos)


def test_extract_videos_single():
    """Single video returns list of one."""
    html = _make_video_wrapper(111, "Birthday Puja")
    videos = _find_videos(html)
    assert len(videos) == 1
    assert videos[0]["slug"] == "Birthday-Puja"


def test_unique_slugs_no_duplicates():
    """Different video names produce different slugs."""
    html = _make_video_wrapper(111, "Krishna Puja") + _make_video_wrapper(222, "Krishna Puja Talk")
    videos = _find_videos(html)
    slugs = [v["slug"] for v in videos]
    assert len(slugs) == len(set(slugs))


def test_duplicate_slugs_get_suffix():
    """Same video name twice should get unique slugs with suffix."""
    html = _make_video_wrapper(111, "Birthday Puja") + _make_video_wrapper(222, "Birthday Puja")
    videos = _find_videos(html)
    slugs = [v["slug"] for v in videos]
    assert len(slugs) == 2
    assert len(set(slugs)) == 2
    assert slugs[0] == "Birthday-Puja"
    assert slugs[1] == "Birthday-Puja-2"


def test_three_duplicate_slugs():
    """Three same names should get -2 and -3 suffixes."""
    html = "".join(_make_video_wrapper(i, "Talk") for i in range(3))
    videos = _find_videos(html)
    slugs = [v["slug"] for v in videos]
    assert slugs == ["Talk", "Talk-2", "Talk-3"]
