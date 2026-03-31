"""Tests for generate_preview.py — Python unit + integration tests."""

import json

import pytest

from tools.generate_preview import (
    generate_index_page,
    generate_site,
    generate_video_page,
    scan_existing_previews,
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


SAMPLE_SRT = """1
00:00:01,000 --> 00:00:05,000
Привіт світе

2
00:00:06,000 --> 00:00:10,000
Другий блок
"""


class TestGenerateVideoPage:
    def setup_method(self):
        self.html = generate_video_page(
            talk_title="Test Talk",
            video_title="Test Video",
            vimeo_embed_url="https://player.vimeo.com/video/12345?h=abc",
            srt_content=SAMPLE_SRT,
            base_url="/sy-subtitles",
        )

    def test_has_doctype(self):
        assert self.html.startswith("<!DOCTYPE html>")

    def test_has_charset(self):
        assert 'charset="utf-8"' in self.html

    def test_has_iframe(self):
        assert "<iframe" in self.html
        assert "player.vimeo.com/video/12345" in self.html

    def test_has_srt_data(self):
        assert 'id="srt-data"' in self.html
        assert "Привіт світе" in self.html

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

    def test_srt_content_preserved(self):
        assert "Другий блок" in self.html


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
        html = generate_index_page(entries, "/base")
        assert "Test Talk" in html
        assert "Video One" in html
        assert "/base/2001-07-29_Test/Video-1/" in html

    def test_empty(self):
        html = generate_index_page([], "")
        assert "No previews yet" in html

    def test_sorted_by_date(self):
        entries = [
            {"talk_id": "b", "talk_title": "ZZZ-Second", "video_slug": "v", "video_title": "V", "date": "2002"},
            {"talk_id": "a", "talk_title": "AAA-First", "video_slug": "v", "video_title": "V", "date": "2001"},
        ]
        html = generate_index_page(entries)
        assert html.index("AAA-First") < html.index("ZZZ-Second")


# --- Integration tests ---


@pytest.fixture
def sample_talk(tmp_path):
    """Create a minimal talk directory structure."""
    talk = tmp_path / "talks" / "2001-01-01_Test-Talk"
    talk.mkdir(parents=True)

    meta = {
        "title": "Test Talk",
        "date": "2001-01-01",
        "videos": [
            {
                "slug": "Test-Video",
                "title": "Test Video Title",
                "vimeo_url": "https://vimeo.com/12345/abcdef",
            }
        ],
    }
    (talk / "meta.yaml").write_text(
        json.dumps(meta).replace("{", "{\n").replace(",", ",\n"),
        encoding="utf-8",
    )

    # Actually write valid YAML
    import yaml

    (talk / "meta.yaml").write_text(yaml.dump(meta, allow_unicode=True), encoding="utf-8")

    video_dir = talk / "Test-Video" / "final"
    video_dir.mkdir(parents=True)
    (video_dir / "uk.srt").write_text(SAMPLE_SRT, encoding="utf-8")

    return talk


def test_generate_site_creates_files(sample_talk, tmp_path):
    out = tmp_path / "site"
    entries = generate_site(str(sample_talk), str(out))
    assert len(entries) == 1
    assert (out / "2001-01-01_Test-Talk" / "Test-Video" / "index.html").exists()


def test_generate_site_html_valid(sample_talk, tmp_path):
    out = tmp_path / "site"
    generate_site(str(sample_talk), str(out))
    html = (out / "2001-01-01_Test-Talk" / "Test-Video" / "index.html").read_text()
    assert "<!DOCTYPE html>" in html
    assert "player.vimeo.com/video/12345" in html
    assert "Привіт світе" in html


def test_scan_existing_previews(tmp_path):
    # Create fake preview structure
    (tmp_path / "2001-01-01_Talk" / "Video-1").mkdir(parents=True)
    (tmp_path / "2001-01-01_Talk" / "Video-1" / "index.html").write_text("<html></html>")
    entries = scan_existing_previews(str(tmp_path))
    assert len(entries) == 1
    assert entries[0]["talk_id"] == "2001-01-01_Talk"
    assert entries[0]["video_slug"] == "Video-1"
