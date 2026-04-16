"""Tests for sync_transcript_to_srt.py."""

import sys

import pytest

from tools.sync_transcript_to_srt import (
    _apply_diff,
    _find_diff,
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

    def test_one_word_change_minimal_diff(self, talk_dir):
        """Changing one word should only affect blocks in that paragraph, preserve everything else."""
        from tools.srt_utils import parse_srt

        srt_before = parse_srt(str(talk_dir / "Video" / "final" / "uk.srt"))
        block_count_before = len(srt_before)
        timecodes_before = [(b["start_ms"], b["end_ms"]) for b in srt_before]

        # Change one word in first paragraph
        new = (
            HEADER + "Перше речення першого параграфу. Друге речення першого абзацу.\n\nЄдине речення другого абзацу.\n"
        )
        new_path = talk_dir / "new.txt"
        new_path.write_text(new, encoding="utf-8")

        result = sync_transcript(str(talk_dir), "Video", str(talk_dir / "transcript_uk_old.txt"), str(new_path))
        assert result["changed"] == 1

        srt_after = parse_srt(str(talk_dir / "Video" / "final" / "uk.srt"))
        # Block count must be identical
        assert len(srt_after) == block_count_before
        # All timecodes must be identical
        timecodes_after = [(b["start_ms"], b["end_ms"]) for b in srt_after]
        assert timecodes_after == timecodes_before
        # Changed block has new text
        assert "параграфу" in srt_after[0]["text"]
        # Unchanged blocks are untouched
        assert srt_after[1]["text"] == srt_before[1]["text"]
        assert srt_after[2]["text"] == srt_before[2]["text"]

    def test_multiple_paragraph_changes_preserve_structure(self, talk_dir):
        """Changing text in both paragraphs should still preserve block count and timecodes."""
        from tools.srt_utils import parse_srt

        srt_before = parse_srt(str(talk_dir / "Video" / "final" / "uk.srt"))
        timecodes_before = [(b["start_ms"], b["end_ms"]) for b in srt_before]

        new = HEADER + "Виправлене перше. Друге речення першого абзацу.\n\nВиправлений другий абзац.\n"
        new_path = talk_dir / "new.txt"
        new_path.write_text(new, encoding="utf-8")

        result = sync_transcript(str(talk_dir), "Video", str(talk_dir / "transcript_uk_old.txt"), str(new_path))
        assert result["changed"] == 2

        srt_after = parse_srt(str(talk_dir / "Video" / "final" / "uk.srt"))
        assert len(srt_after) == len(srt_before)
        timecodes_after = [(b["start_ms"], b["end_ms"]) for b in srt_after]
        assert timecodes_after == timecodes_before


class TestSyncBlockCountChange:
    """Block-count-change edits (edits that cross CPL boundaries) must return
    an error — text-only sync can't fabricate timing without whisper. See
    feedback_no_proportional. Callers should fall back to the full pipeline."""

    def test_block_count_change_errors_out(self, talk_dir):
        """When an edit grows a sentence past the CPL limit so it splits into
        more blocks, sync_transcript must return an error instead of
        redistributing timecodes proportionally."""
        new = (
            HEADER
            + "Перше дуже довге речення першого абзацу яке тепер має набагато більше тексту і буде розбите інакше."
            + " Друге речення першого абзацу.\n\nЄдине речення другого абзацу.\n"
        )
        new_path = talk_dir / "new.txt"
        new_path.write_text(new, encoding="utf-8")

        result = sync_transcript(str(talk_dir), "Video", str(talk_dir / "transcript_uk_old.txt"), str(new_path))
        assert "error" in result
        assert "pipeline" in result["error"].lower()

    def test_block_count_change_leaves_srt_untouched(self, talk_dir):
        """On block-count error the SRT file must not be modified — partial
        rewrites are banned by feedback_no_proportional."""
        from tools.srt_utils import parse_srt

        srt_before = parse_srt(str(talk_dir / "Video" / "final" / "uk.srt"))
        new = (
            HEADER
            + "Перше дуже довге речення першого абзацу яке тепер має набагато більше тексту і буде розбите інакше."
            + " Друге речення першого абзацу.\n\nЄдине речення другого абзацу.\n"
        )
        new_path = talk_dir / "new.txt"
        new_path.write_text(new, encoding="utf-8")

        sync_transcript(str(talk_dir), "Video", str(talk_dir / "transcript_uk_old.txt"), str(new_path))

        srt_after = parse_srt(str(talk_dir / "Video" / "final" / "uk.srt"))
        assert len(srt_after) == len(srt_before)
        for a, b in zip(srt_after, srt_before, strict=True):
            assert a == b

    def test_same_block_count_succeeds(self, talk_dir):
        """Unchanged block count is the happy path — result has no error,
        no legacy needs_optimize flag."""
        new = HEADER + "Виправлене перше речення. Друге речення першого абзацу.\n\nЄдине речення другого абзацу.\n"
        new_path = talk_dir / "new.txt"
        new_path.write_text(new, encoding="utf-8")

        result = sync_transcript(str(talk_dir), "Video", str(talk_dir / "transcript_uk_old.txt"), str(new_path))
        assert "error" not in result
        assert "needs_optimize" not in result

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


class TestMismatchedBlockSplits:
    """SRT blocks built by whisper pipeline may combine sentences that
    prepare_blocks would split separately.  sync_transcript must still
    handle text replacements via difflib fragment matching."""

    @pytest.fixture
    def mismatched_talk(self, tmp_path):
        """SRT block 2 has TWO sentences combined (46 CPL).
        prepare_blocks would split them into separate blocks."""
        talk = tmp_path / "talks" / "test"
        video = talk / "Video" / "final"
        video.mkdir(parents=True)

        srt = (
            "1\n00:00:01,000 --> 00:00:05,000\n"
            "Перше речення абзацу.\n\n"
            "2\n00:00:05,100 --> 00:00:10,000\n"
            "Друге речення абзацу. Третє коротке!\n\n"
            "3\n00:00:12,000 --> 00:00:18,000\n"
            "Другий абзац тут.\n"
        )
        (video / "uk.srt").write_text(srt, encoding="utf-8")

        old = HEADER + "Перше речення абзацу. Друге речення абзацу. Третє коротке!\n\n" + "Другий абзац тут.\n"
        (talk / "old.txt").write_text(old, encoding="utf-8")
        return talk

    def test_single_word_replacement(self, mismatched_talk):
        """Changing one word in a combined SRT block must succeed."""
        new = HEADER + "Перше речення абзацу. Змінене речення абзацу. Третє коротке!\n\n" + "Другий абзац тут.\n"
        new_path = mismatched_talk / "new.txt"
        new_path.write_text(new, encoding="utf-8")

        result = sync_transcript(
            str(mismatched_talk),
            "Video",
            str(mismatched_talk / "old.txt"),
            str(new_path),
        )

        assert "error" not in result
        assert result["changed"] == 1

        from tools.srt_utils import parse_srt

        srt = parse_srt(str(mismatched_talk / "Video" / "final" / "uk.srt"))
        assert srt[1]["text"] == "Змінене речення абзацу. Третє коротке!"

    def test_multiple_fragments_same_block(self, mismatched_talk):
        """Two changes landing in the same combined SRT block."""
        new = HEADER + "Перше речення абзацу. Змінене речення абзацу. Третє довге!\n\n" + "Другий абзац тут.\n"
        new_path = mismatched_talk / "new.txt"
        new_path.write_text(new, encoding="utf-8")

        result = sync_transcript(
            str(mismatched_talk),
            "Video",
            str(mismatched_talk / "old.txt"),
            str(new_path),
        )

        assert "error" not in result

        from tools.srt_utils import parse_srt

        srt = parse_srt(str(mismatched_talk / "Video" / "final" / "uk.srt"))
        assert srt[1]["text"] == "Змінене речення абзацу. Третє довге!"

    def test_preserves_timecodes(self, mismatched_talk):
        """All timecodes must remain intact — only text changes."""
        from tools.srt_utils import parse_srt

        before = [(b["start_ms"], b["end_ms"]) for b in parse_srt(str(mismatched_talk / "Video" / "final" / "uk.srt"))]

        new = HEADER + "Перше речення абзацу. Змінене речення абзацу. Третє коротке!\n\n" + "Другий абзац тут.\n"
        new_path = mismatched_talk / "new.txt"
        new_path.write_text(new, encoding="utf-8")

        sync_transcript(
            str(mismatched_talk),
            "Video",
            str(mismatched_talk / "old.txt"),
            str(new_path),
        )

        after = [(b["start_ms"], b["end_ms"]) for b in parse_srt(str(mismatched_talk / "Video" / "final" / "uk.srt"))]
        assert after == before

    def test_unchanged_blocks_not_touched(self, mismatched_talk):
        """Blocks outside the changed paragraph must be untouched."""
        new = HEADER + "Перше речення абзацу. Змінене речення абзацу. Третє коротке!\n\n" + "Другий абзац тут.\n"
        new_path = mismatched_talk / "new.txt"
        new_path.write_text(new, encoding="utf-8")

        sync_transcript(
            str(mismatched_talk),
            "Video",
            str(mismatched_talk / "old.txt"),
            str(new_path),
        )

        from tools.srt_utils import parse_srt

        srt = parse_srt(str(mismatched_talk / "Video" / "final" / "uk.srt"))
        assert srt[0]["text"] == "Перше речення абзацу."
        assert srt[2]["text"] == "Другий абзац тут."

    def test_cpl_exceeded_after_replacement(self, tmp_path):
        """Replacement that pushes a block over MAX_CPL must error."""
        talk = tmp_path / "talks" / "test"
        video = talk / "Video" / "final"
        video.mkdir(parents=True)

        # Block 1 is 78 CPL — close to the 84 limit
        srt = (
            "1\n00:00:01,000 --> 00:00:05,000\n"
            "Дуже довге речення абзацу яке має сімдесят вісім символів для тесту ось тут.\n\n"
            "2\n00:00:12,000 --> 00:00:18,000\n"
            "Другий абзац.\n"
        )
        (video / "uk.srt").write_text(srt, encoding="utf-8")

        old = (
            HEADER
            + "Дуже довге речення абзацу яке має сімдесят вісім символів для тесту ось тут.\n\n"
            + "Другий абзац.\n"
        )
        (talk / "old.txt").write_text(old, encoding="utf-8")

        # Replace "тут" (3 chars) with longer text to exceed 84 CPL
        new = (
            HEADER
            + "Дуже довге речення абзацу яке має сімдесят вісім символів для тесту ось тут-тут-тут-тут.\n\n"
            + "Другий абзац.\n"
        )
        new_path = talk / "new.txt"
        new_path.write_text(new, encoding="utf-8")

        result = sync_transcript(
            str(talk),
            "Video",
            str(talk / "old.txt"),
            str(new_path),
        )

        assert "error" in result
        assert "CPL" in result["error"] or "cpl" in result["error"].lower()

    def test_real_world_pr84_scenario(self, tmp_path):
        """Reproduce PR #84: SRT combines two sentences into one block,
        prepare_blocks would split them. Two phrase replacements must work."""
        talk = tmp_path / "talks" / "test"
        video = talk / "Video" / "final"
        video.mkdir(parents=True)

        srt = (
            "1\n00:00:01,000 --> 00:00:05,000\n"
            "Вона може створити майю.\n\n"
            "2\n00:00:05,100 --> 00:00:15,000\n"
            "І це створило велику майю в умах людей, що «Ми на вершині світу!». Ви – ні!\n\n"
            "3\n00:00:15,100 --> 00:00:20,000\n"
            "Другий абзац.\n"
        )
        (video / "uk.srt").write_text(srt, encoding="utf-8")

        old = (
            HEADER
            + "Вона може створити майю. "
            + "І це створило велику майю в умах людей, що «Ми на вершині світу!». Ви – ні!\n\n"
            + "Другий абзац.\n"
        )
        (talk / "old.txt").write_text(old, encoding="utf-8")

        new = (
            HEADER
            + "Вона може створити майю. "
            + "І це створило велику майю в свідомості людей, що «Ми на вершині світу!». Це не так!\n\n"
            + "Другий абзац.\n"
        )
        new_path = talk / "new.txt"
        new_path.write_text(new, encoding="utf-8")

        result = sync_transcript(
            str(talk),
            "Video",
            str(talk / "old.txt"),
            str(new_path),
        )

        assert "error" not in result
        assert result["changed"] == 1

        from tools.srt_utils import parse_srt

        srt_blocks = parse_srt(str(talk / "Video" / "final" / "uk.srt"))
        assert srt_blocks[1]["text"] == (
            "І це створило велику майю в свідомості людей, що «Ми на вершині світу!». Це не так!"
        )
        assert len(srt_blocks[1]["text"]) <= 84
        assert srt_blocks[1]["start_ms"] == 5100
        assert srt_blocks[1]["end_ms"] == 15000


class TestFindDiff:
    """Unit tests for _find_diff helper."""

    def test_single_word_change(self):
        old_f, new_f = _find_diff("Перше речення абзацу.", "Перше речення параграфу.")
        # Prefix/suffix trimming: common suffix "у." is trimmed
        assert "абзац" in old_f
        assert "парагра" in new_f or "параграф" in new_f

    def test_empty_old_returns_empty(self):
        old_f, _ = _find_diff("", "нове")
        assert old_f == ""

    def test_multiple_changes(self):
        old_f, new_f = _find_diff("AAAA. Текст. BBBB!", "CCCC. Текст. DDDD!")
        # Both changes captured in one fragment
        assert "AAAA" in old_f
        assert "BBBB" in old_f
        assert "CCCC" in new_f
        assert "DDDD" in new_f


class TestApplyDiffEdgeCases:
    """Edge cases for _apply_diff."""

    def test_empty_old_frag_errors(self):
        result = _apply_diff("", "нове", [], 0)
        assert "error" in result
        assert "cannot determine" in result["error"]

    def test_frag_not_found_in_blocks(self):
        blocks = [{"text": "Зовсім інший текст."}]
        result = _apply_diff("Перше.", "Друге.", blocks, 0)
        assert "error" in result
        assert "cannot find" in result["error"]


class TestMain:
    """CLI entry point coverage (in-process for coverage tracking)."""

    def test_main_success(self, talk_dir, monkeypatch):
        new = HEADER + "Виправлене перше речення. Друге речення першого абзацу.\n\nЄдине речення другого абзацу.\n"
        new_path = talk_dir / "new.txt"
        new_path.write_text(new, encoding="utf-8")

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "sync_transcript_to_srt",
                "--talk-dir",
                str(talk_dir),
                "--video-slug",
                "Video",
                "--old-transcript",
                str(talk_dir / "transcript_uk_old.txt"),
                "--new-transcript",
                str(new_path),
            ],
        )
        from tools.sync_transcript_to_srt import main

        main()  # should not raise

    def test_main_no_changes(self, talk_dir, monkeypatch, capsys):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "sync_transcript_to_srt",
                "--talk-dir",
                str(talk_dir),
                "--video-slug",
                "Video",
                "--old-transcript",
                str(talk_dir / "transcript_uk_old.txt"),
                "--new-transcript",
                str(talk_dir / "transcript_uk.txt"),
            ],
        )
        from tools.sync_transcript_to_srt import main

        main()
        assert "No changes" in capsys.readouterr().err

    def test_main_error(self, talk_dir, monkeypatch, capsys):
        (talk_dir / "Video" / "final" / "uk.srt").unlink()
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "sync_transcript_to_srt",
                "--talk-dir",
                str(talk_dir),
                "--video-slug",
                "Video",
                "--old-transcript",
                str(talk_dir / "transcript_uk_old.txt"),
                "--new-transcript",
                str(talk_dir / "transcript_uk.txt"),
            ],
        )
        from tools.sync_transcript_to_srt import main

        with pytest.raises(SystemExit, match="1"):
            main()
        assert "FAIL" in capsys.readouterr().err
