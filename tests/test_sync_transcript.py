"""Tests for sync_transcript_to_srt.py."""

import pytest

from tools.sync_transcript_to_srt import (
    find_paragraph_blocks,
    prepare_blocks,
    sync_transcript,
)

HEADER = "Мова промови: англійська | Транскрипт (українська)\n\n"


@pytest.fixture
def talk_dir(tmp_path):
    """Create a minimal talk with SRT."""
    talk = tmp_path / "talks" / "test"
    video = talk / "Video" / "final"
    video.mkdir(parents=True)

    srt_content = """1
00:00:01,000 --> 00:00:05,000
Перше речення першого абзацу.

2
00:00:05,100 --> 00:00:10,000
Друге речення першого абзацу.

3
00:00:12,000 --> 00:00:18,000
Єдине речення другого абзацу.
"""
    (video / "uk.srt").write_text(srt_content, encoding="utf-8")

    old_transcript = (
        HEADER + "Перше речення першого абзацу. Друге речення першого абзацу.\n\nЄдине речення другого абзацу.\n"
    )
    (talk / "transcript_uk_old.txt").write_text(old_transcript, encoding="utf-8")
    (talk / "transcript_uk.txt").write_text(old_transcript, encoding="utf-8")

    return talk


class TestPrepareBlocks:
    def test_single_paragraph(self):
        blocks = prepare_blocks(["Перше речення. Друге речення."])
        assert len(blocks) == 2
        assert blocks[0]["text"] == "Перше речення."
        assert blocks[1]["text"] == "Друге речення."

    def test_preserves_para_idx(self):
        blocks = prepare_blocks(["Абзац один.", "Абзац два."])
        assert blocks[0]["para_idx"] == 0
        assert blocks[1]["para_idx"] == 1

    def test_long_sentence_split(self):
        long = "Це дуже довге речення яке має бути розбите на кілька рядків щоб вміститися в обмеження вісімдесят чотири символи на рядок."
        blocks = prepare_blocks([long])
        assert len(blocks) >= 2
        for b in blocks:
            assert len(b["text"]) <= 84


class TestFindParagraphBlocks:
    def test_finds_match(self):
        srt = [{"text": "A"}, {"text": "B"}, {"text": "C"}]
        assert find_paragraph_blocks(srt, [{"text": "B"}, {"text": "C"}]) == [1, 2]

    def test_finds_at_start(self):
        srt = [{"text": "A"}, {"text": "B"}]
        assert find_paragraph_blocks(srt, [{"text": "A"}]) == [0]

    def test_not_found(self):
        assert find_paragraph_blocks([{"text": "A"}], [{"text": "X"}]) is None

    def test_empty(self):
        assert find_paragraph_blocks([], [{"text": "A"}]) is None
        assert find_paragraph_blocks([{"text": "A"}], []) is None


class TestSyncTextSwap:
    def test_swap_first_paragraph(self, talk_dir):
        new = HEADER + "Виправлене перше речення. Друге речення першого абзацу.\n\nЄдине речення другого абзацу.\n"
        new_path = talk_dir / "new.txt"
        new_path.write_text(new, encoding="utf-8")

        result = sync_transcript(str(talk_dir), "Video", str(talk_dir / "transcript_uk_old.txt"), str(new_path))
        assert result["changed"] == 1
        assert result["updated_blocks"] == 2

        from tools.srt_utils import parse_srt

        srt = parse_srt(str(talk_dir / "Video" / "final" / "uk.srt"))
        assert srt[0]["text"] == "Виправлене перше речення."
        assert srt[0]["start_ms"] == 1000  # timecode preserved
        assert srt[0]["end_ms"] == 5000

    def test_swap_second_paragraph(self, talk_dir):
        new = HEADER + "Перше речення першого абзацу. Друге речення першого абзацу.\n\nВиправлений другий абзац.\n"
        new_path = talk_dir / "new.txt"
        new_path.write_text(new, encoding="utf-8")

        result = sync_transcript(str(talk_dir), "Video", str(talk_dir / "transcript_uk_old.txt"), str(new_path))
        assert result["changed"] == 1

        from tools.srt_utils import parse_srt

        srt = parse_srt(str(talk_dir / "Video" / "final" / "uk.srt"))
        assert srt[2]["text"] == "Виправлений другий абзац."
        assert srt[2]["start_ms"] == 12000  # preserved

    def test_no_changes(self, talk_dir):
        result = sync_transcript(
            str(talk_dir), "Video", str(talk_dir / "transcript_uk_old.txt"), str(talk_dir / "transcript_uk.txt")
        )
        assert result["changed"] == 0

    def test_unchanged_blocks_preserved(self, talk_dir):
        new = HEADER + "Виправлено. Друге речення першого абзацу.\n\nЄдине речення другого абзацу.\n"
        new_path = talk_dir / "new.txt"
        new_path.write_text(new, encoding="utf-8")

        sync_transcript(str(talk_dir), "Video", str(talk_dir / "transcript_uk_old.txt"), str(new_path))

        from tools.srt_utils import parse_srt

        srt = parse_srt(str(talk_dir / "Video" / "final" / "uk.srt"))
        assert srt[1]["text"] == "Друге речення першого абзацу."
        assert srt[1]["start_ms"] == 5100
        assert srt[2]["text"] == "Єдине речення другого абзацу."
        assert srt[2]["start_ms"] == 12000


class TestSyncFails:
    def test_block_count_change_fails(self, talk_dir):
        """When edit changes CPL split count — fail, need full rebuild."""
        new = (
            HEADER
            + "Перше дуже довге речення першого абзацу яке тепер має набагато більше тексту і буде розбите інакше."
            + " Друге речення першого абзацу.\n\nЄдине речення другого абзацу.\n"
        )
        new_path = talk_dir / "new.txt"
        new_path.write_text(new, encoding="utf-8")

        result = sync_transcript(str(talk_dir), "Video", str(talk_dir / "transcript_uk_old.txt"), str(new_path))
        assert "error" in result
        assert "block count" in result["error"].lower() or "need full rebuild" in result["error"].lower()

    def test_paragraph_count_mismatch_fails(self, talk_dir):
        new = HEADER + "Тільки один абзац.\n"
        new_path = talk_dir / "new.txt"
        new_path.write_text(new, encoding="utf-8")

        result = sync_transcript(str(talk_dir), "Video", str(talk_dir / "transcript_uk_old.txt"), str(new_path))
        assert "error" in result

    def test_no_srt_fails(self, talk_dir):
        (talk_dir / "Video" / "final" / "uk.srt").unlink()
        result = sync_transcript(
            str(talk_dir), "Video", str(talk_dir / "transcript_uk_old.txt"), str(talk_dir / "transcript_uk.txt")
        )
        assert "error" in result

    def test_blocks_not_found_fails(self, talk_dir):
        """SRT text doesn't match transcript — fail."""
        srt_path = talk_dir / "Video" / "final" / "uk.srt"
        srt_path.write_text("1\n00:00:01,000 --> 00:00:05,000\nЗовсім інший текст.\n", encoding="utf-8")

        new = HEADER + "Виправлено. Друге речення першого абзацу.\n\nЄдине речення другого абзацу.\n"
        new_path = talk_dir / "new.txt"
        new_path.write_text(new, encoding="utf-8")

        result = sync_transcript(str(talk_dir), "Video", str(talk_dir / "transcript_uk_old.txt"), str(new_path))
        assert "error" in result
