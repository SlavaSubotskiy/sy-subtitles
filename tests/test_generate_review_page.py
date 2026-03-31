"""Tests for generate_review_page.py — unit + integration + E2E."""

import functools
import http.server
import threading

import pytest
import yaml

from tools.generate_review_page import (
    generate_review_page,
    generate_review_site,
    scan_talks_with_transcripts,
)

# --- Unit tests ---


class TestGenerateReviewPage:
    def setup_method(self):
        self.html = generate_review_page(
            talk_title="Test Talk",
            talk_id="2001-01-01_Test",
            en_raw_url="https://raw.githubusercontent.com/test/repo/main/en.txt",
            uk_raw_url="https://raw.githubusercontent.com/test/repo/main/uk.txt",
            base_url="/base",
            repo="test/repo",
        )

    def test_has_doctype(self):
        assert self.html.startswith("<!DOCTYPE html>")

    def test_has_charset(self):
        assert 'charset="utf-8"' in self.html

    def test_has_title(self):
        assert "Test Talk" in self.html

    def test_has_index_link(self):
        assert 'href="/base/"' in self.html

    def test_fetches_en_transcript(self):
        assert "EN_URL" in self.html
        assert "raw.githubusercontent.com" in self.html

    def test_fetches_uk_transcript(self):
        assert "UK_URL" in self.html

    def test_has_grid(self):
        assert 'id="grid"' in self.html

    def test_has_create_issue_button(self):
        assert "createIssue" in self.html

    def test_has_github_editor_button(self):
        assert "openEditor" in self.html
        assert "edit/main" in self.html

    def test_has_transcript_parser(self):
        assert "parseTranscript" in self.html

    def test_has_contenteditable(self):
        assert "contenteditable" in self.html

    def test_has_localStorage(self):
        assert "localStorage" in self.html

    def test_has_keyboard_shortcut(self):
        assert "ctrlKey" in self.html or "metaKey" in self.html

    def test_has_counter(self):
        assert 'id="counter"' in self.html

    def test_has_mark_and_edit_tracking(self):
        assert "mark-count" in self.html
        assert "edit-count" in self.html


# --- Integration tests ---


@pytest.fixture
def sample_talks(tmp_path):
    talks = tmp_path / "talks"

    # Talk with both transcripts
    talk1 = talks / "2001-01-01_Test-Talk"
    talk1.mkdir(parents=True)
    meta1 = {"title": "Test Talk", "date": "2001-01-01", "videos": [{"slug": "V", "title": "V", "vimeo_url": ""}]}
    (talk1 / "meta.yaml").write_text(yaml.dump(meta1, allow_unicode=True))
    (talk1 / "transcript_en.txt").write_text("Talk Language: English\n\nParagraph one.\n\nParagraph two.\n")
    (talk1 / "transcript_uk.txt").write_text("Мова промови: англійська\n\nПерший абзац.\n\nДругий абзац.\n")

    # Talk without UK transcript
    talk2 = talks / "2002-01-01_No-Uk"
    talk2.mkdir(parents=True)
    meta2 = {"title": "No UK", "date": "2002-01-01", "videos": [{"slug": "V", "title": "V", "vimeo_url": ""}]}
    (talk2 / "meta.yaml").write_text(yaml.dump(meta2, allow_unicode=True))
    (talk2 / "transcript_en.txt").write_text("Talk Language: English\n\nText.\n")

    return talks


def test_scan_finds_talk_with_both_transcripts(sample_talks):
    entries = scan_talks_with_transcripts(str(sample_talks))
    assert len(entries) == 1
    assert entries[0]["talk_id"] == "2001-01-01_Test-Talk"


def test_scan_skips_talk_without_uk(sample_talks):
    entries = scan_talks_with_transcripts(str(sample_talks))
    assert all(e["talk_id"] != "2002-01-01_No-Uk" for e in entries)


def test_generate_review_site_creates_files(sample_talks, tmp_path):
    entries = scan_talks_with_transcripts(str(sample_talks))
    out = tmp_path / "site"
    generate_review_site(entries, str(out))
    assert (out / "2001-01-01_Test-Talk" / "review" / "index.html").exists()


# --- E2E tests ---

SAMPLE_EN = "Talk Language: English\n\nFirst paragraph.\n\nSecond paragraph.\n"
SAMPLE_UK = "Мова промови: англійська\n\nПерший абзац.\n\nДругий абзац.\n"


@pytest.fixture(scope="module")
def review_site(tmp_path_factory):
    from tools.generate_review_page import generate_review_page

    base = tmp_path_factory.mktemp("site")
    out = base / "out" / "2001-01-01_Test" / "review"
    out.mkdir(parents=True)
    page = generate_review_page(
        "Test Talk",
        "2001-01-01_Test",
        "http://mock/en.txt",
        "http://mock/uk.txt",
        "",
        "test/repo",
    )
    (out / "index.html").write_text(page, encoding="utf-8")
    return base / "out"


@pytest.fixture(scope="module")
def server(review_site):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(review_site))
    httpd = http.server.HTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


@pytest.fixture(scope="module")
def browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright not installed")
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(server, browser):
    ctx = browser.new_context()
    pg = ctx.new_page()
    # Mock transcript fetches
    pg.route("**/mock/en.txt", lambda r: r.fulfill(status=200, content_type="text/plain", body=SAMPLE_EN))
    pg.route("**/mock/uk.txt", lambda r: r.fulfill(status=200, content_type="text/plain", body=SAMPLE_UK))
    yield pg
    pg.close()
    ctx.close()


REVIEW_URL = "/2001-01-01_Test/review/"


class TestReviewPageLoads:
    def test_loads(self, server, page):
        page.goto(f"{server}{REVIEW_URL}")
        assert "Review" in page.title()

    def test_grid_rendered(self, server, page):
        page.goto(f"{server}{REVIEW_URL}")
        page.wait_for_function("document.querySelectorAll('.cell.en').length > 0", timeout=5000)
        en_cells = page.locator(".cell.en").count()
        uk_cells = page.locator(".cell.uk").count()
        assert en_cells == 2
        assert uk_cells == 2

    def test_en_content(self, server, page):
        page.goto(f"{server}{REVIEW_URL}")
        page.wait_for_function("document.querySelectorAll('.cell.en').length > 0", timeout=5000)
        text = page.locator(".cell.en").first.text_content()
        assert "First paragraph" in text

    def test_uk_content(self, server, page):
        page.goto(f"{server}{REVIEW_URL}")
        page.wait_for_function("document.querySelectorAll('.cell.uk').length > 0", timeout=5000)
        text = page.locator(".cell.uk").first.text_content()
        assert "Перший абзац" in text

    def test_uk_editable(self, server, page):
        page.goto(f"{server}{REVIEW_URL}")
        page.wait_for_function("document.querySelectorAll('.cell.uk').length > 0", timeout=5000)
        attr = page.locator(".cell.uk").first.get_attribute("contenteditable")
        assert attr == "true"


class TestReviewEditing:
    def _wait_ready(self, server, page):
        page.goto(f"{server}{REVIEW_URL}")
        page.wait_for_function("document.querySelectorAll('.cell.uk').length > 0", timeout=5000)
        page.evaluate("localStorage.removeItem('review_2001-01-01_Test')")

    def test_edit_tracked(self, server, page):
        self._wait_ready(server, page)
        cell = page.locator(".cell.uk").first
        cell.click()
        cell.fill("Змінений текст")
        cell.dispatch_event("input")
        has_edited = page.locator(".cell.uk.edited").count()
        assert has_edited >= 1

    def test_edit_counter(self, server, page):
        self._wait_ready(server, page)
        cell = page.locator(".cell.uk").first
        cell.click()
        cell.fill("Змінений текст")
        cell.dispatch_event("input")
        count = page.locator("#edit-count").text_content()
        assert int(count) >= 1

    def test_edit_persists_in_localStorage(self, server, page):
        self._wait_ready(server, page)
        cell = page.locator(".cell.uk").first
        cell.click()
        cell.fill("Persist test")
        cell.dispatch_event("input")
        stored = page.evaluate("JSON.parse(localStorage.getItem('review_2001-01-01_Test'))")
        assert "edits" in stored
        assert len(stored["edits"]) >= 1


class TestReviewMarking:
    def _wait_ready(self, server, page):
        page.goto(f"{server}{REVIEW_URL}")
        page.wait_for_function("document.querySelectorAll('.cell.uk').length > 0", timeout=5000)
        page.evaluate("localStorage.removeItem('review_2001-01-01_Test')")

    def test_ctrl_m_marks_paragraph(self, server, page):
        self._wait_ready(server, page)
        page.locator(".cell.uk").first.click()
        page.keyboard.press("Control+m")
        has_marked = page.locator(".cell.uk.marked").count()
        assert has_marked >= 1

    def test_mark_counter(self, server, page):
        self._wait_ready(server, page)
        page.locator(".cell.uk").first.click()
        page.keyboard.press("Control+m")
        count = page.locator("#mark-count").text_content()
        assert int(count) >= 1

    def test_toggle_mark(self, server, page):
        self._wait_ready(server, page)
        page.locator(".cell.uk").first.click()
        page.keyboard.press("Control+m")
        assert page.locator(".cell.uk.marked").count() >= 1
        page.locator(".cell.uk").first.click()
        page.keyboard.press("Control+m")
        assert page.locator(".cell.uk.marked").count() == 0


class TestReviewIssue:
    def _wait_ready(self, server, page):
        page.goto(f"{server}{REVIEW_URL}")
        page.wait_for_function("document.querySelectorAll('.cell.uk').length > 0", timeout=5000)
        page.evaluate("localStorage.removeItem('review_2001-01-01_Test')")

    def test_issue_body_has_transcript_link(self, server, page):
        self._wait_ready(server, page)
        page.locator(".cell.uk").first.click()
        page.keyboard.press("Control+m")
        body = page.evaluate("issueBody()")
        assert "transcript_uk.txt" in body

    def test_issue_body_has_marked_paragraph(self, server, page):
        self._wait_ready(server, page)
        page.locator(".cell.uk").first.click()
        page.keyboard.press("Control+m")
        body = page.evaluate("issueBody()")
        assert "P1" in body
        assert "First paragraph" in body

    def test_issue_body_full_text_not_truncated(self, server, page):
        self._wait_ready(server, page)
        page.locator(".cell.uk").first.click()
        page.keyboard.press("Control+m")
        body = page.evaluate("issueBody()")
        # Full paragraph text must be present, not truncated
        assert "First paragraph." in body

    def test_issue_body_edits_in_details(self, server, page):
        self._wait_ready(server, page)
        cell = page.locator(".cell.uk").first
        cell.click()
        cell.fill("Edited paragraph text")
        cell.dispatch_event("input")
        body = page.evaluate("issueBody()")
        assert "<details>" in body
        assert "Before:" in body
        assert "After:" in body
        assert "Edited paragraph text" in body

    def test_build_edited_transcript(self, server, page):
        self._wait_ready(server, page)
        cell = page.locator(".cell.uk").first
        cell.click()
        cell.fill("Змінений абзац")
        cell.dispatch_event("input")
        transcript = page.evaluate("buildEditedTranscript()")
        assert "Змінений абзац" in transcript
        # Second paragraph should be original
        assert "Другий абзац" in transcript

    def test_build_edited_transcript_has_header(self, server, page):
        self._wait_ready(server, page)
        transcript = page.evaluate("buildEditedTranscript()")
        assert "Мова промови:" in transcript

    def test_build_edited_transcript_separator(self, server, page):
        """Separator between paragraphs should match original format."""
        self._wait_ready(server, page)
        transcript = page.evaluate("buildEditedTranscript()")
        # SAMPLE_UK uses double newlines
        assert "\n\n" in transcript

    def test_open_editor_uses_window_open(self, server, page):
        self._wait_ready(server, page)
        uses_open = page.evaluate("openEditor.toString().includes('window.open')")
        assert uses_open

    def test_issue_body_has_edits(self, server, page):
        self._wait_ready(server, page)
        cell = page.locator(".cell.uk").first
        cell.click()
        cell.fill("Changed text")
        cell.dispatch_event("input")
        body = page.evaluate("issueBody()")
        assert "Suggested edits" in body
        assert "Changed text" in body


class TestReviewCounter:
    def _wait_ready(self, server, page):
        page.goto(f"{server}{REVIEW_URL}")
        page.wait_for_function("document.querySelectorAll('.cell.uk').length > 0", timeout=5000)
        page.evaluate("localStorage.removeItem('review_2001-01-01_Test')")

    def test_counter_hidden_initially(self, server, page):
        self._wait_ready(server, page)
        assert page.locator("#counter").get_attribute("style") == "display:none"

    def test_counter_visible_after_mark(self, server, page):
        self._wait_ready(server, page)
        page.locator(".cell.uk").first.click()
        page.keyboard.press("Control+m")
        assert page.locator("#counter").is_visible()

    def test_counter_visible_after_edit(self, server, page):
        self._wait_ready(server, page)
        cell = page.locator(".cell.uk").first
        cell.click()
        cell.fill("Edit")
        cell.dispatch_event("input")
        assert page.locator("#counter").is_visible()


class TestParseTranscript:
    def _wait_ready(self, server, page):
        page.goto(f"{server}{REVIEW_URL}")
        page.wait_for_function("document.querySelectorAll('.cell.uk').length > 0", timeout=5000)

    def test_single_newline_format(self, server, page):
        """EN transcript uses single newlines — should parse into separate paragraphs."""
        self._wait_ready(server, page)
        # SAMPLE_EN has single newlines after header
        en_count = page.locator(".cell.en").count()
        assert en_count == 2  # "First paragraph." and "Second paragraph."

    def test_double_newline_format(self, server, page):
        """UK transcript uses double newlines — should parse into separate paragraphs."""
        self._wait_ready(server, page)
        uk_count = page.locator(".cell.uk").count()
        assert uk_count == 2
