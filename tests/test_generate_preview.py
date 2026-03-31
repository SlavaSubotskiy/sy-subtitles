"""Tests for generate_preview.py — Python unit + integration tests."""

import pytest
import yaml

from tools.generate_preview import (
    generate_index_page,
    generate_site,
    generate_video_page,
    scan_all_talks,
    vimeo_url_to_embed,
)

# --- Unit tests ---


class TestVimeoUrlToEmbed:
    def test_standard(self):
        url = "https://vimeo.com/88444291/558a575bd0"
        assert vimeo_url_to_embed(url) == "https://player.vimeo.com/video/88444291?h=558a575bd0"

    def test_already_embed(self):
        url = "https://player.vimeo.com/video/12345?h=abc"
        assert vimeo_url_to_embed(url) == url

    def test_empty(self):
        assert vimeo_url_to_embed("") == ""

    def test_http(self):
        url = "http://vimeo.com/12345/abcdef"
        assert "player.vimeo.com" in vimeo_url_to_embed(url)


SAMPLE_SRT_URL = "https://raw.githubusercontent.com/test/repo/main/talks/test/V/final/uk.srt"


class TestGenerateVideoPage:
    def setup_method(self):
        self.html = generate_video_page(
            talk_title="Test Talk",
            video_title="Test Video",
            vimeo_embed_url="https://player.vimeo.com/video/12345?h=abc",
            srt_raw_url=SAMPLE_SRT_URL,
            base_url="/sy-subtitles",
        )

    def test_has_doctype(self):
        assert self.html.startswith("<!DOCTYPE html>")

    def test_has_charset(self):
        assert 'charset="utf-8"' in self.html

    def test_has_iframe(self):
        assert "<iframe" in self.html
        assert "player.vimeo.com/video/12345" in self.html

    def test_fetches_srt_dynamically(self):
        assert "fetch(" in self.html
        assert SAMPLE_SRT_URL in self.html

    def test_no_embedded_srt(self):
        assert 'id="srt-data"' not in self.html

    def test_has_player_sdk(self):
        assert "player.vimeo.com/api/player.js" in self.html

    def test_has_subtitle_overlay(self):
        assert 'id="subtitle-overlay"' in self.html

    def test_has_parseSRT_function(self):
        assert "function parseSRT" in self.html

    def test_has_title(self):
        assert "Test Talk" in self.html
        assert "Test Video" in self.html

    def test_has_index_link(self):
        assert 'href="/sy-subtitles/"' in self.html

    def test_has_loading_status(self):
        assert "Loading subtitles" in self.html


class TestGenerateIndexPage:
    def test_with_entries(self):
        entries = [
            {
                "talk_id": "2001-07-29_Test",
                "talk_title": "Test Talk",
                "video_slug": "Video-1",
                "video_title": "Video One",
                "date": "2001-07-29",
            }
        ]
        result = generate_index_page(entries, base_url="/base")
        assert "Test Talk" in result
        assert "Video One" in result
        assert "/base/2001-07-29_Test/Video-1/" in result

    def test_with_review_entries(self):
        entries = [{"talk_id": "t1", "talk_title": "Talk", "video_slug": "v", "video_title": "V", "date": "2001"}]
        reviews = [{"talk_id": "t1", "talk_title": "Talk", "date": "2001"}]
        result = generate_index_page(entries, reviews, "/base")
        assert "review translation" in result
        assert "/base/t1/review/" in result

    def test_empty(self):
        result = generate_index_page([], base_url="")
        assert "No previews yet" in result

    def test_sorted_by_date(self):
        entries = [
            {"talk_id": "b", "talk_title": "ZZZ-Second", "video_slug": "v", "video_title": "V", "date": "2002"},
            {"talk_id": "a", "talk_title": "AAA-First", "video_slug": "v", "video_title": "V", "date": "2001"},
        ]
        result = generate_index_page(entries, base_url="")
        assert result.index("AAA-First") < result.index("ZZZ-Second")


# --- Integration tests ---


@pytest.fixture
def sample_talks(tmp_path):
    """Create minimal talk directory structure."""
    talks = tmp_path / "talks"

    talk1 = talks / "2001-01-01_Test-Talk"
    talk1.mkdir(parents=True)
    meta1 = {
        "title": "Test Talk",
        "date": "2001-01-01",
        "videos": [
            {"slug": "Test-Video", "title": "Test Video Title", "vimeo_url": "https://vimeo.com/12345/abcdef"},
        ],
    }
    (talk1 / "meta.yaml").write_text(yaml.dump(meta1, allow_unicode=True), encoding="utf-8")
    video_dir = talk1 / "Test-Video" / "final"
    video_dir.mkdir(parents=True)
    (video_dir / "uk.srt").write_text("1\n00:00:01,000 --> 00:00:05,000\nTest\n", encoding="utf-8")

    # Talk without SRT — should be skipped
    talk2 = talks / "2002-01-01_No-Srt"
    talk2.mkdir(parents=True)
    meta2 = {"title": "No SRT", "date": "2002-01-01", "videos": [{"slug": "V", "title": "V", "vimeo_url": ""}]}
    (talk2 / "meta.yaml").write_text(yaml.dump(meta2, allow_unicode=True), encoding="utf-8")

    return talks


def test_scan_all_talks(sample_talks):
    entries = scan_all_talks(str(sample_talks))
    assert len(entries) == 1
    assert entries[0]["talk_id"] == "2001-01-01_Test-Talk"


def test_generate_site_creates_files(sample_talks, tmp_path):
    entries = scan_all_talks(str(sample_talks))
    out = tmp_path / "site"
    generate_site(entries, str(out))
    assert (out / "index.html").exists()
    assert (out / "2001-01-01_Test-Talk" / "Test-Video" / "index.html").exists()


def test_generated_html_fetches_srt(sample_talks, tmp_path):
    entries = scan_all_talks(str(sample_talks))
    out = tmp_path / "site"
    generate_site(entries, str(out))
    page = (out / "2001-01-01_Test-Talk" / "Test-Video" / "index.html").read_text()
    assert "fetch(" in page
    assert "raw.githubusercontent.com" in page
    assert "uk.srt" in page
