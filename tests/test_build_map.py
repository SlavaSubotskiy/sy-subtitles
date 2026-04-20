"""Tests for tools.build_map and tools.text_segmentation."""

import argparse
import json

from tools.build_map import (
    TC_RE,
    _normalize,
    cmd_assemble,
    cmd_prepare,
    cmd_prepare_timing,
)
from tools.text_segmentation import build_blocks_from_paragraphs

# ---------------------------------------------------------------------------
# _normalize
# ---------------------------------------------------------------------------


class TestNormalize:
    def test_lowercase(self):
        assert _normalize("Hello") == "hello"

    def test_strip_punctuation(self):
        assert _normalize("word,") == "word"
        assert _normalize("(hello)") == "hello"
        assert _normalize("end.") == "end"

    def test_mixed_punctuation(self):
        assert _normalize("it's") == "its"
        assert _normalize('"quoted"') == "quoted"

    def test_ukrainian(self):
        assert _normalize("Привіт") == "привіт"
        assert _normalize("СЛОВО!") == "слово"

    def test_empty(self):
        assert _normalize("") == ""

    def test_punctuation_only(self):
        assert _normalize("...") == ""
        assert _normalize("—") == ""

    def test_numbers(self):
        assert _normalize("123") == "123"
        assert _normalize("word42") == "word42"

    def test_single_word(self):
        assert _normalize("word") == "word"


# ---------------------------------------------------------------------------
# build_blocks_from_paragraphs (canonical subtitle block builder)
# ---------------------------------------------------------------------------


class TestBuildBlocksFromParagraphs:
    def test_single_paragraph_single_sentence(self):
        paras = ["Коротке речення."]
        blocks = build_blocks_from_paragraphs(paras)
        assert len(blocks) == 1
        assert blocks[0]["id"] == 1
        assert blocks[0]["text"] == "Коротке речення."
        assert blocks[0]["para_idx"] == 0

    def test_single_paragraph_multiple_sentences(self):
        paras = ["Перше речення. Друге речення."]
        blocks = build_blocks_from_paragraphs(paras)
        assert len(blocks) >= 2
        assert blocks[0]["id"] == 1
        assert blocks[1]["id"] == 2
        # All blocks belong to paragraph 0
        assert all(b["para_idx"] == 0 for b in blocks)

    def test_multiple_paragraphs(self):
        paras = ["Перший абзац.", "Другий абзац."]
        blocks = build_blocks_from_paragraphs(paras)
        assert len(blocks) == 2
        assert blocks[0]["para_idx"] == 0
        assert blocks[1]["para_idx"] == 1

    def test_ids_sequential(self):
        paras = ["Перше.", "Друге.", "Третє."]
        blocks = build_blocks_from_paragraphs(paras)
        for i, b in enumerate(blocks):
            assert b["id"] == i + 1

    def test_cpl_constraint(self):
        """All blocks must be <= 84 characters per line."""
        long_text = "Це дуже довге речення яке містить набагато більше ніж вісімдесят чотири символи тому повинно бути розділене на менші частини для субтитрів."
        paras = [long_text]
        blocks = build_blocks_from_paragraphs(paras)
        for b in blocks:
            assert len(b["text"]) <= 84, f"Block too long ({len(b['text'])} CPL): {b['text']}"

    def test_empty_paragraphs(self):
        blocks = build_blocks_from_paragraphs([])
        assert blocks == []

    def test_preserves_text(self):
        """All original text should appear across blocks."""
        paras = ["Перше речення.", "Друге речення."]
        blocks = build_blocks_from_paragraphs(paras)
        all_text = " ".join(b["text"] for b in blocks)
        assert "Перше речення." in all_text
        assert "Друге речення." in all_text

    def test_paragraph_index_tracking(self):
        """Blocks from different paragraphs have correct para_idx."""
        paras = ["Перше.", "Друге.", "Третє."]
        blocks = build_blocks_from_paragraphs(paras)
        assert blocks[0]["para_idx"] == 0
        assert blocks[1]["para_idx"] == 1
        assert blocks[2]["para_idx"] == 2

    def test_single_word_paragraph(self):
        blocks = build_blocks_from_paragraphs(["Слово"])
        assert len(blocks) == 1
        assert blocks[0]["text"] == "Слово"

    def test_very_long_paragraph(self):
        """Very long paragraph splits into multiple blocks, all <= 84 CPL."""
        words = ["слово"] * 100
        paras = [" ".join(words)]
        blocks = build_blocks_from_paragraphs(paras)
        assert len(blocks) > 1
        for b in blocks:
            assert len(b["text"]) <= 84

    def test_blocks_cover_all_words(self):
        """All words from paragraphs appear across blocks in order."""
        paras = ["Перше речення.", "Друге речення."]
        blocks = build_blocks_from_paragraphs(paras)
        block_words = []
        for b in blocks:
            block_words.extend(b["text"].split())
        para_words = []
        for p in paras:
            para_words.extend(p.split())
        assert block_words == para_words


# ---------------------------------------------------------------------------
# cmd_prepare (integration via file system)
# ---------------------------------------------------------------------------


class TestCmdPrepare:
    def _setup_talk_dir(
        self, tmp_path, uk_text="Перший абзац.\n\nДругий абзац.", en_text="First paragraph.\n\nSecond paragraph."
    ):
        """Set up a minimal talk directory structure."""
        talk_dir = tmp_path / "talk"
        video_dir = talk_dir / "video1"
        source_dir = video_dir / "source"
        source_dir.mkdir(parents=True)

        (talk_dir / "transcript_uk.txt").write_text(uk_text, encoding="utf-8")
        (talk_dir / "transcript_en.txt").write_text(en_text, encoding="utf-8")

        whisper_data = {
            "segments": [
                {
                    "start": 0.0,
                    "end": 3.0,
                    "text": " First paragraph.",
                    "words": [
                        {"word": " First", "start": 0.0, "end": 0.5},
                        {"word": " paragraph.", "start": 0.5, "end": 3.0},
                    ],
                },
                {
                    "start": 4.0,
                    "end": 7.0,
                    "text": " Second paragraph.",
                    "words": [
                        {"word": " Second", "start": 4.0, "end": 4.5},
                        {"word": " paragraph.", "start": 4.5, "end": 7.0},
                    ],
                },
            ]
        }
        (source_dir / "whisper.json").write_text(json.dumps(whisper_data), encoding="utf-8")
        return talk_dir

    def test_prepare_creates_uk_blocks(self, tmp_path):
        talk_dir = self._setup_talk_dir(tmp_path)
        args = argparse.Namespace(talk_dir=str(talk_dir), video_slug="video1", timing_source="whisper")
        cmd_prepare(args)

        blocks_file = talk_dir / "video1" / "work" / "uk_blocks.json"
        assert blocks_file.exists(), "uk_blocks.json not created"
        blocks = json.loads(blocks_file.read_text(encoding="utf-8"))
        assert isinstance(blocks, list)
        assert len(blocks) >= 2

    def test_prepare_uk_blocks_json_structure(self, tmp_path):
        talk_dir = self._setup_talk_dir(tmp_path)
        args = argparse.Namespace(talk_dir=str(talk_dir), video_slug="video1", timing_source="whisper")
        cmd_prepare(args)

        blocks_file = talk_dir / "video1" / "work" / "uk_blocks.json"
        loaded = json.loads(blocks_file.read_text(encoding="utf-8"))
        assert isinstance(loaded, list)
        for block in loaded:
            assert "id" in block
            assert "text" in block
            assert "para_idx" in block


# ---------------------------------------------------------------------------
# cmd_prepare_timing (integration via file system)
# ---------------------------------------------------------------------------


class TestCmdPrepareTiming:
    def _setup_talk_dir(self, tmp_path):
        talk_dir = tmp_path / "talk"
        video_dir = talk_dir / "video1"
        source_dir = video_dir / "source"
        source_dir.mkdir(parents=True)
        (talk_dir / "transcript_uk.txt").write_text("Тест.", encoding="utf-8")

        whisper_data = {
            "segments": [
                {
                    "start": 1.0,
                    "end": 3.0,
                    "text": " Hello world",
                    "words": [
                        {"word": "Hello", "start": 1.0, "end": 1.5},
                        {"word": "world", "start": 1.5, "end": 3.0},
                    ],
                }
            ]
        }
        (source_dir / "whisper.json").write_text(json.dumps(whisper_data), encoding="utf-8")

        # Minimal EN SRT
        en_srt_text = "1\n00:00:01,000 --> 00:00:03,000\nHello world\n\n2\n00:00:04,000 --> 00:00:06,000\nSecond line\n"
        (source_dir / "en.srt").write_text(en_srt_text, encoding="utf-8")

        return talk_dir

    def test_prepare_timing_whisper(self, tmp_path):
        """cmd_prepare_timing writes timing.json with whisper word-level data."""
        talk_dir = self._setup_talk_dir(tmp_path)
        work = talk_dir / "video1" / "work"
        work.mkdir(parents=True, exist_ok=True)

        args = argparse.Namespace(talk_dir=str(talk_dir), video_slug="video1", timing_source="whisper")
        cmd_prepare_timing(args)

        timing_file = work / "timing.json"
        assert timing_file.exists(), "timing.json not created"
        data = json.loads(timing_file.read_text(encoding="utf-8"))
        assert data["source"] == "whisper"
        assert "words" in data
        assert isinstance(data["words"], list)
        assert len(data["words"]) > 0
        # Each word entry must have w, s, e keys
        for entry in data["words"]:
            assert "w" in entry
            assert "s" in entry
            assert "e" in entry

    def test_prepare_timing_en_srt(self, tmp_path):
        """cmd_prepare_timing --timing-source en-srt writes timing.json with SRT blocks."""
        talk_dir = self._setup_talk_dir(tmp_path)
        work = talk_dir / "video1" / "work"
        work.mkdir(parents=True, exist_ok=True)

        args = argparse.Namespace(talk_dir=str(talk_dir), video_slug="video1", timing_source="en-srt")
        cmd_prepare_timing(args)

        timing_file = work / "timing.json"
        assert timing_file.exists(), "timing.json not created"
        data = json.loads(timing_file.read_text(encoding="utf-8"))
        assert data["source"] == "en-srt"
        assert "blocks" in data
        assert isinstance(data["blocks"], list)
        assert len(data["blocks"]) == 2
        # Each block entry must have n, s, e, t keys
        for block in data["blocks"]:
            assert "n" in block
            assert "s" in block
            assert "e" in block
            assert "t" in block


# ---------------------------------------------------------------------------
# cmd_assemble (integration via file system)
# ---------------------------------------------------------------------------


class TestCmdAssemble:
    def _setup_assemble_dir(self, tmp_path, n_blocks=5, provide_timecodes=True):
        """Set up work directory with uk_blocks.json and optionally timecodes.txt."""
        work = tmp_path / "talk" / "video1" / "work"
        work.mkdir(parents=True, exist_ok=True)
        final = tmp_path / "talk" / "video1" / "final"
        final.mkdir(parents=True, exist_ok=True)

        blocks = [{"id": i + 1, "text": f"Блок {i + 1}.", "para_idx": 0} for i in range(n_blocks)]
        (work / "uk_blocks.json").write_text(json.dumps(blocks, ensure_ascii=False), encoding="utf-8")

        if provide_timecodes:
            lines = []
            for bid in range(1, n_blocks + 1):
                start_ms = bid * 2000
                end_ms = start_ms + 1500
                start_tc = f"00:00:{start_ms // 1000:02d},{start_ms % 1000:03d}"
                end_tc = f"00:00:{end_ms // 1000:02d},{end_ms % 1000:03d}"
                lines.append(f"#{bid} | {start_tc} | {end_tc}")
            (work / "timecodes.txt").write_text("\n".join(lines), encoding="utf-8")

        return work

    def test_assemble_from_timecodes(self, tmp_path):
        """cmd_assemble reads timecodes.txt + uk_blocks.json → writes uk.srt directly."""
        self._setup_assemble_dir(tmp_path, n_blocks=3)

        args = argparse.Namespace(talk_dir=str(tmp_path / "talk"), video_slug="video1")
        cmd_assemble(args)

        srt_file = tmp_path / "talk" / "video1" / "final" / "uk.srt"
        assert srt_file.exists(), "uk.srt not created"
        content = srt_file.read_text(encoding="utf-8")
        # Must contain all 3 block texts
        for i in range(1, 4):
            assert f"Блок {i}." in content
        # Must NOT write uk.map as intermediate
        assert not (tmp_path / "talk" / "video1" / "work" / "uk.map").exists(), "uk.map should not be produced"

    def test_assemble_missing_timecodes_file(self, tmp_path):
        """Missing timecodes.txt → cmd_assemble exits with error."""
        import pytest

        self._setup_assemble_dir(tmp_path, n_blocks=3, provide_timecodes=False)

        args = argparse.Namespace(talk_dir=str(tmp_path / "talk"), video_slug="video1")
        with pytest.raises(SystemExit) as exc_info:
            cmd_assemble(args)
        assert exc_info.value.code != 0

    def test_assemble_missing_block(self, tmp_path):
        """timecodes.txt with a missing block ID → cmd_assemble exits with error."""
        import pytest

        work = self._setup_assemble_dir(tmp_path, n_blocks=5, provide_timecodes=False)
        # Write timecodes for only 4 of 5 blocks (block 5 missing)
        lines = []
        for bid in range(1, 5):
            start_ms = bid * 2000
            end_ms = start_ms + 1500
            start_tc = f"00:00:{start_ms // 1000:02d},{start_ms % 1000:03d}"
            end_tc = f"00:00:{end_ms // 1000:02d},{end_ms % 1000:03d}"
            lines.append(f"#{bid} | {start_tc} | {end_tc}")
        (work / "timecodes.txt").write_text("\n".join(lines), encoding="utf-8")

        args = argparse.Namespace(talk_dir=str(tmp_path / "talk"), video_slug="video1")
        with pytest.raises(SystemExit) as exc_info:
            cmd_assemble(args)
        assert exc_info.value.code != 0

    def test_assemble_timecode_regex_parsing(self):
        """Verify TC_RE parses various timecode formats."""
        # Standard format
        m = TC_RE.search("#1 | 00:00:01,000 | 00:00:03,500")
        assert m
        assert m.group(1) == "1"
        assert m.group(2) == "00:00:01,000"
        assert m.group(3) == "00:00:03,500"

        # No spaces
        m = TC_RE.search("#42|01:23:45,678|01:23:50,000")
        assert m
        assert m.group(1) == "42"

        # Extra text around
        m = TC_RE.search("  #100 | 00:05:00,000 | 00:05:05,000  some trailing text")
        assert m
        assert m.group(1) == "100"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_punctuation_only_normalize(self):
        assert _normalize("!!!") == ""
        assert _normalize(".,;:") == ""
        assert _normalize("—") == ""

    def test_normalize_with_apostrophe(self):
        assert _normalize("it's") == "its"
        assert _normalize("don't") == "dont"

    def test_normalize_with_hyphen(self):
        # Hyphen is \W, so it gets stripped
        assert _normalize("well-known") == "wellknown"
