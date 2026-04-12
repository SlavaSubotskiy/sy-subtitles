"""Tests for sync_srt_to_transcript.py."""

import pytest

from tools.sync_srt_to_transcript import sync_srt_to_transcript
from tools.sync_transcript_to_srt import sync_transcript

HEADER = "Мова промови: англійська | Транскрипт (українська)\n\n"


@pytest.fixture
def talk(tmp_path):
    """Talk with one video, an SRT and a transcript that match."""
    talk_dir = tmp_path / "talks" / "test"
    video = talk_dir / "Video" / "final"
    video.mkdir(parents=True)

    srt_old = """1
00:00:01,000 --> 00:00:05,000
Перше речення першого абзацу.

2
00:00:05,100 --> 00:00:10,000
Друге речення першого абзацу.

3
00:00:12,000 --> 00:00:18,000
Єдине речення другого абзацу.
"""
    (video / "uk.srt").write_text(srt_old, encoding="utf-8")
    (talk_dir / "uk_old.srt").write_text(srt_old, encoding="utf-8")

    transcript = (
        HEADER + "Перше речення першого абзацу. Друге речення першого абзацу.\n\nЄдине речення другого абзацу.\n"
    )
    (talk_dir / "transcript_uk.txt").write_text(transcript, encoding="utf-8")

    return talk_dir


class TestSyncSrtToTranscript:
    def test_no_changes_returns_zero(self, talk):
        result = sync_srt_to_transcript(
            old_srt=str(talk / "uk_old.srt"),
            new_srt=str(talk / "Video" / "final" / "uk.srt"),
            transcript=str(talk / "transcript_uk.txt"),
        )
        assert result["changed"] == 0

    def test_single_block_edit_propagates(self, talk):
        new_srt_path = talk / "Video" / "final" / "uk.srt"
        new_srt = """1
00:00:01,000 --> 00:00:05,000
Виправлене перше речення.

2
00:00:05,100 --> 00:00:10,000
Друге речення першого абзацу.

3
00:00:12,000 --> 00:00:18,000
Єдине речення другого абзацу.
"""
        new_srt_path.write_text(new_srt, encoding="utf-8")

        result = sync_srt_to_transcript(
            old_srt=str(talk / "uk_old.srt"),
            new_srt=str(new_srt_path),
            transcript=str(talk / "transcript_uk.txt"),
        )
        assert result["changed"] == 1
        text = (talk / "transcript_uk.txt").read_text(encoding="utf-8")
        assert "Виправлене перше речення." in text
        assert "Перше речення першого абзацу." not in text
        # Other paragraphs untouched
        assert "Друге речення першого абзацу." in text
        assert "Єдине речення другого абзацу." in text

    def test_multiple_block_edits_propagate(self, talk):
        new_srt = """1
00:00:01,000 --> 00:00:05,000
Виправлене перше.

2
00:00:05,100 --> 00:00:10,000
Друге речення першого абзацу.

3
00:00:12,000 --> 00:00:18,000
Виправлений другий.
"""
        (talk / "Video" / "final" / "uk.srt").write_text(new_srt, encoding="utf-8")

        result = sync_srt_to_transcript(
            old_srt=str(talk / "uk_old.srt"),
            new_srt=str(talk / "Video" / "final" / "uk.srt"),
            transcript=str(talk / "transcript_uk.txt"),
        )
        assert result["changed"] == 2
        text = (talk / "transcript_uk.txt").read_text(encoding="utf-8")
        assert "Виправлене перше." in text
        assert "Виправлений другий." in text
        assert "Перше речення першого абзацу." not in text
        assert "Єдине речення другого абзацу." not in text

    def test_block_inserted_fails(self, talk):
        """Inserting a brand-new block (no place to put text in transcript) is unsupported."""
        new_srt = """1
00:00:01,000 --> 00:00:05,000
Перше речення першого абзацу.

2
00:00:05,100 --> 00:00:10,000
Друге речення першого абзацу.

3
00:00:10,500 --> 00:00:11,500
Новий вставлений блок.

4
00:00:12,000 --> 00:00:18,000
Єдине речення другого абзацу.
"""
        (talk / "Video" / "final" / "uk.srt").write_text(new_srt, encoding="utf-8")

        result = sync_srt_to_transcript(
            old_srt=str(talk / "uk_old.srt"),
            new_srt=str(talk / "Video" / "final" / "uk.srt"),
            transcript=str(talk / "transcript_uk.txt"),
        )
        assert "error" in result

    def test_deleted_placeholder_block_skipped_silently(self, tmp_path):
        """Deleting a block whose text is NOT in the transcript (e.g. a placeholder
        like '[Промова англійською]') should succeed without touching the transcript."""
        talk_dir = tmp_path / "talk"
        video = talk_dir / "Video" / "final"
        video.mkdir(parents=True)

        old_srt = """1
00:00:00,000 --> 00:00:02,000
[Промова англійською]

2
00:00:03,000 --> 00:00:05,000
Перше справжнє речення.

3
00:00:05,100 --> 00:00:10,000
Друге речення.
"""
        new_srt = """2
00:00:03,000 --> 00:00:05,000
Перше справжнє речення.

3
00:00:05,100 --> 00:00:10,000
Друге речення.
"""
        (talk_dir / "uk_old.srt").write_text(old_srt, encoding="utf-8")
        (video / "uk.srt").write_text(new_srt, encoding="utf-8")

        transcript = HEADER + "Перше справжнє речення. Друге речення.\n"
        (talk_dir / "transcript_uk.txt").write_text(transcript, encoding="utf-8")
        before = transcript

        result = sync_srt_to_transcript(
            old_srt=str(talk_dir / "uk_old.srt"),
            new_srt=str(video / "uk.srt"),
            transcript=str(talk_dir / "transcript_uk.txt"),
        )
        assert "error" not in result, f"unexpected error: {result.get('error')}"
        assert (talk_dir / "transcript_uk.txt").read_text(encoding="utf-8") == before

    def test_deleted_block_present_in_transcript_is_removed(self, tmp_path):
        """If a deleted block's text IS in the transcript, it should be removed."""
        talk_dir = tmp_path / "talk"
        video = talk_dir / "Video" / "final"
        video.mkdir(parents=True)

        old_srt = """1
00:00:01,000 --> 00:00:03,000
Перше речення.

2
00:00:03,100 --> 00:00:05,000
Зайве речення.

3
00:00:05,100 --> 00:00:08,000
Третє речення.
"""
        new_srt = """1
00:00:01,000 --> 00:00:03,000
Перше речення.

3
00:00:05,100 --> 00:00:08,000
Третє речення.
"""
        (talk_dir / "uk_old.srt").write_text(old_srt, encoding="utf-8")
        (video / "uk.srt").write_text(new_srt, encoding="utf-8")

        transcript = HEADER + "Перше речення. Зайве речення. Третє речення.\n"
        (talk_dir / "transcript_uk.txt").write_text(transcript, encoding="utf-8")

        result = sync_srt_to_transcript(
            old_srt=str(talk_dir / "uk_old.srt"),
            new_srt=str(video / "uk.srt"),
            transcript=str(talk_dir / "transcript_uk.txt"),
        )
        assert "error" not in result
        text = (talk_dir / "transcript_uk.txt").read_text(encoding="utf-8")
        assert "Зайве речення." not in text
        assert "Перше речення." in text
        assert "Третє речення." in text

    def test_renumbers_new_srt_after_deletion(self, tmp_path):
        """When the user's SRT skipped renumbering after deleting blocks, the
        tool should normalize block indices to start at 1 and be sequential."""
        talk_dir = tmp_path / "talk"
        video = talk_dir / "Video" / "final"
        video.mkdir(parents=True)

        old_srt = """1
00:00:00,000 --> 00:00:02,000
[Placeholder]

2
00:00:03,000 --> 00:00:05,000
Перше речення.

3
00:00:05,100 --> 00:00:08,000
Друге речення.
"""
        # User removed block 1 but did NOT renumber — block "2" is now first
        new_srt = """2
00:00:03,000 --> 00:00:05,000
Перше речення.

3
00:00:05,100 --> 00:00:08,000
Друге речення.
"""
        (talk_dir / "uk_old.srt").write_text(old_srt, encoding="utf-8")
        (video / "uk.srt").write_text(new_srt, encoding="utf-8")
        (talk_dir / "transcript_uk.txt").write_text(HEADER + "Перше речення. Друге речення.\n", encoding="utf-8")

        result = sync_srt_to_transcript(
            old_srt=str(talk_dir / "uk_old.srt"),
            new_srt=str(video / "uk.srt"),
            transcript=str(talk_dir / "transcript_uk.txt"),
        )
        assert "error" not in result

        from tools.srt_utils import parse_srt

        new_blocks = parse_srt(str(video / "uk.srt"))
        assert [b["idx"] for b in new_blocks] == [1, 2]
        # Texts and timecodes preserved
        assert new_blocks[0]["text"] == "Перше речення."
        assert new_blocks[0]["start_ms"] == 3000
        assert new_blocks[1]["text"] == "Друге речення."

    def test_drift_in_unchanged_blocks_does_not_fail_delete_only_pr(self, tmp_path):
        """Real-world drift: an unchanged SRT block has a wording that doesn't
        match the transcript verbatim (e.g. capitalization, missing word). For a
        delete-only PR the cursor anchor isn't needed, so the tool should treat
        this as a benign warning, not an error."""
        talk_dir = tmp_path / "talk"
        video = talk_dir / "Video" / "final"
        video.mkdir(parents=True)

        old_srt = """1
00:00:00,000 --> 00:00:02,000
[Placeholder]

2
00:00:03,000 --> 00:00:05,000
Перше речення.

3
00:00:05,100 --> 00:00:08,000
Але Бог – це особистість, яка поза запитаннями.

4
00:00:08,100 --> 00:00:10,000
Третє речення.
"""
        new_srt = """2
00:00:03,000 --> 00:00:05,000
Перше речення.

3
00:00:05,100 --> 00:00:08,000
Але Бог – це особистість, яка поза запитаннями.

4
00:00:08,100 --> 00:00:10,000
Третє речення.
"""
        (talk_dir / "uk_old.srt").write_text(old_srt, encoding="utf-8")
        (video / "uk.srt").write_text(new_srt, encoding="utf-8")
        # Transcript has the SAME sentence but with different capitalization and
        # an extra word — drift the SRT had at edit time.
        (talk_dir / "transcript_uk.txt").write_text(
            HEADER + "Перше речення. Але Бог – це Особистість, яка перебуває поза запитаннями. Третє речення.\n",
            encoding="utf-8",
        )
        before = (talk_dir / "transcript_uk.txt").read_text(encoding="utf-8")

        result = sync_srt_to_transcript(
            old_srt=str(talk_dir / "uk_old.srt"),
            new_srt=str(video / "uk.srt"),
            transcript=str(talk_dir / "transcript_uk.txt"),
        )
        assert "error" not in result, f"unexpected error: {result.get('error')}"
        # Transcript untouched (placeholder wasn't there, drift is left alone)
        assert (talk_dir / "transcript_uk.txt").read_text(encoding="utf-8") == before

    def test_pr43_scenario_two_leading_placeholders_removed(self, tmp_path):
        """Reproduces PR #43: user removed two leading placeholder blocks
        ([Промова англійською]) that were never in the transcript."""
        talk_dir = tmp_path / "talk"
        video = talk_dir / "Video" / "final"
        video.mkdir(parents=True)

        old_srt = """1
00:00:00,000 --> 00:00:02,920
[Промова англійською]

2
00:00:03,000 --> 00:00:05,920
на англійську]

3
00:00:06,000 --> 00:00:09,500
Шрі Матаджі зауважила: «Це була улюблена пісня».

4
00:00:09,580 --> 00:00:16,850
Багато людей завжди запитували Мене.
"""
        new_srt = """3
00:00:06,000 --> 00:00:09,500
Шрі Матаджі зауважила: «Це була улюблена пісня».

4
00:00:09,580 --> 00:00:16,850
Багато людей завжди запитували Мене.
"""
        (talk_dir / "uk_old.srt").write_text(old_srt, encoding="utf-8")
        (video / "uk.srt").write_text(new_srt, encoding="utf-8")
        (talk_dir / "transcript_uk.txt").write_text(
            HEADER + "Шрі Матаджі зауважила: «Це була улюблена пісня». Багато людей завжди запитували Мене.\n",
            encoding="utf-8",
        )
        before = (talk_dir / "transcript_uk.txt").read_text(encoding="utf-8")

        result = sync_srt_to_transcript(
            old_srt=str(talk_dir / "uk_old.srt"),
            new_srt=str(video / "uk.srt"),
            transcript=str(talk_dir / "transcript_uk.txt"),
        )
        assert "error" not in result, f"unexpected error: {result.get('error')}"
        # Transcript untouched (placeholders weren't there)
        assert (talk_dir / "transcript_uk.txt").read_text(encoding="utf-8") == before
        # SRT renumbered to 1, 2
        from tools.srt_utils import parse_srt

        blocks = parse_srt(str(video / "uk.srt"))
        assert [b["idx"] for b in blocks] == [1, 2]

    def test_old_text_not_in_transcript_fails(self, talk):
        # Make transcript drift from SRT
        (talk / "transcript_uk.txt").write_text(HEADER + "Зовсім інший текст.\n\nДругий абзац.\n", encoding="utf-8")
        new_srt = """1
00:00:01,000 --> 00:00:05,000
Виправлене перше речення.

2
00:00:05,100 --> 00:00:10,000
Друге речення першого абзацу.

3
00:00:12,000 --> 00:00:18,000
Єдине речення другого абзацу.
"""
        (talk / "Video" / "final" / "uk.srt").write_text(new_srt, encoding="utf-8")

        result = sync_srt_to_transcript(
            old_srt=str(talk / "uk_old.srt"),
            new_srt=str(talk / "Video" / "final" / "uk.srt"),
            transcript=str(talk / "transcript_uk.txt"),
        )
        assert "error" in result

    def test_no_changes_does_not_rewrite_file(self, talk):
        """When nothing changed the transcript file should be byte-identical."""
        before = (talk / "transcript_uk.txt").read_bytes()
        sync_srt_to_transcript(
            old_srt=str(talk / "uk_old.srt"),
            new_srt=str(talk / "Video" / "final" / "uk.srt"),
            transcript=str(talk / "transcript_uk.txt"),
        )
        after = (talk / "transcript_uk.txt").read_bytes()
        assert before == after

    def test_unchanged_paragraphs_byte_identical(self, talk):
        """Paragraphs not touched by an edit must remain byte-identical (no whitespace shuffle)."""
        new_srt = """1
00:00:01,000 --> 00:00:05,000
Виправлене перше речення.

2
00:00:05,100 --> 00:00:10,000
Друге речення першого абзацу.

3
00:00:12,000 --> 00:00:18,000
Єдине речення другого абзацу.
"""
        (talk / "Video" / "final" / "uk.srt").write_text(new_srt, encoding="utf-8")
        sync_srt_to_transcript(
            old_srt=str(talk / "uk_old.srt"),
            new_srt=str(talk / "Video" / "final" / "uk.srt"),
            transcript=str(talk / "transcript_uk.txt"),
        )
        text = (talk / "transcript_uk.txt").read_text(encoding="utf-8")
        # Header preserved verbatim
        assert text.startswith(HEADER)
        # Second paragraph preserved verbatim with surrounding newlines
        assert "\n\nЄдине речення другого абзацу.\n" in text
        # Edit landed on first sentence, surrounding text preserved
        assert "Виправлене перше речення. Друге речення першого абзацу." in text

    def test_special_characters_in_edit(self, talk):
        """Edits with quotes/punctuation/em-dashes go through cleanly."""
        new_srt = """1
00:00:01,000 --> 00:00:05,000
«Цитата» — з тире.

2
00:00:05,100 --> 00:00:10,000
Друге речення першого абзацу.

3
00:00:12,000 --> 00:00:18,000
Єдине речення другого абзацу.
"""
        (talk / "Video" / "final" / "uk.srt").write_text(new_srt, encoding="utf-8")
        result = sync_srt_to_transcript(
            old_srt=str(talk / "uk_old.srt"),
            new_srt=str(talk / "Video" / "final" / "uk.srt"),
            transcript=str(talk / "transcript_uk.txt"),
        )
        assert result["changed"] == 1
        text = (talk / "transcript_uk.txt").read_text(encoding="utf-8")
        assert "«Цитата» — з тире." in text

    def test_bom_srt_supported(self, talk):
        """SRT files with UTF-8 BOM (project allows it) should still parse."""
        new_srt = """1
00:00:01,000 --> 00:00:05,000
Виправлене перше речення.

2
00:00:05,100 --> 00:00:10,000
Друге речення першого абзацу.

3
00:00:12,000 --> 00:00:18,000
Єдине речення другого абзацу.
"""
        # Write both old and new with BOM
        (talk / "uk_old.srt").write_text("\ufeff" + (talk / "uk_old.srt").read_text(encoding="utf-8"), encoding="utf-8")
        (talk / "Video" / "final" / "uk.srt").write_text("\ufeff" + new_srt, encoding="utf-8")
        result = sync_srt_to_transcript(
            old_srt=str(talk / "uk_old.srt"),
            new_srt=str(talk / "Video" / "final" / "uk.srt"),
            transcript=str(talk / "transcript_uk.txt"),
        )
        assert result["changed"] == 1
        assert "Виправлене перше речення." in (talk / "transcript_uk.txt").read_text(encoding="utf-8")

    def test_cli_entrypoint_writes_file(self, talk):
        """The module CLI should run end-to-end and update the transcript."""
        import subprocess
        import sys

        new_srt = """1
00:00:01,000 --> 00:00:05,000
CLI правка.

2
00:00:05,100 --> 00:00:10,000
Друге речення першого абзацу.

3
00:00:12,000 --> 00:00:18,000
Єдине речення другого абзацу.
"""
        (talk / "Video" / "final" / "uk.srt").write_text(new_srt, encoding="utf-8")
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.sync_srt_to_transcript",
                "--old-srt",
                str(talk / "uk_old.srt"),
                "--new-srt",
                str(talk / "Video" / "final" / "uk.srt"),
                "--transcript",
                str(talk / "transcript_uk.txt"),
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        assert "CLI правка." in (talk / "transcript_uk.txt").read_text(encoding="utf-8")

    def test_cli_exits_nonzero_on_error(self, talk):
        """CLI should exit 1 when block count mismatches."""
        import subprocess
        import sys

        bad_srt = "1\n00:00:01,000 --> 00:00:02,000\nLone block.\n"
        (talk / "Video" / "final" / "uk.srt").write_text(bad_srt, encoding="utf-8")
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.sync_srt_to_transcript",
                "--old-srt",
                str(talk / "uk_old.srt"),
                "--new-srt",
                str(talk / "Video" / "final" / "uk.srt"),
                "--transcript",
                str(talk / "transcript_uk.txt"),
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        assert "FAIL" in proc.stderr

    def test_round_trip_propagates_to_other_videos(self, tmp_path):
        """End-to-end: SRT edit on Video1 → transcript → re-sync to Video2.

        This mirrors what sync-subtitles.yml does for a multi-video talk:
        an edit in one video's SRT must end up in the other video's SRT.
        """
        talk_dir = tmp_path / "talks" / "test"
        for slug in ("Video1", "Video2"):
            (talk_dir / slug / "final").mkdir(parents=True)

        common_srt = """1
00:00:01,000 --> 00:00:05,000
Перше речення першого абзацу.

2
00:00:05,100 --> 00:00:10,000
Друге речення першого абзацу.

3
00:00:12,000 --> 00:00:18,000
Єдине речення другого абзацу.
"""
        (talk_dir / "Video1" / "final" / "uk.srt").write_text(common_srt, encoding="utf-8")
        (talk_dir / "Video2" / "final" / "uk.srt").write_text(common_srt, encoding="utf-8")
        (talk_dir / "old_video1.srt").write_text(common_srt, encoding="utf-8")
        transcript = HEADER + (
            "Перше речення першого абзацу. Друге речення першого абзацу.\n\nЄдине речення другого абзацу.\n"
        )
        (talk_dir / "transcript_uk.txt").write_text(transcript, encoding="utf-8")
        # Save base-SHA copy of transcript for the second sync step
        (talk_dir / "old_transcript.txt").write_text(transcript, encoding="utf-8")

        # Step A: edit Video1's SRT
        edited_srt = common_srt.replace("Перше речення першого абзацу.", "Виправлене перше речення.")
        (talk_dir / "Video1" / "final" / "uk.srt").write_text(edited_srt, encoding="utf-8")

        # Step B: propagate edit to transcript
        result = sync_srt_to_transcript(
            old_srt=str(talk_dir / "old_video1.srt"),
            new_srt=str(talk_dir / "Video1" / "final" / "uk.srt"),
            transcript=str(talk_dir / "transcript_uk.txt"),
        )
        assert result["changed"] == 1

        # Step C: re-sync transcript → Video2's SRT (simulates the workflow's
        # second pass that propagates to *all* videos in the talk)
        sync_result = sync_transcript(
            talk_dir=str(talk_dir),
            video_slug="Video2",
            old_transcript=str(talk_dir / "old_transcript.txt"),
            new_transcript=str(talk_dir / "transcript_uk.txt"),
        )
        assert "error" not in sync_result
        assert sync_result["changed"] == 1

        # Video2 now has the edit applied
        v2 = (talk_dir / "Video2" / "final" / "uk.srt").read_text(encoding="utf-8")
        assert "Виправлене перше речення." in v2
        assert "Перше речення першого абзацу." not in v2
        # Other blocks untouched, timecodes preserved
        assert "00:00:05,100 --> 00:00:10,000" in v2
        assert "Друге речення першого абзацу." in v2

    def test_repeated_block_text_replaces_correct_occurrence(self, tmp_path):
        """If the same text appears in two blocks, editing the second must
        replace the second occurrence in the transcript, not the first."""
        talk_dir = tmp_path / "talk"
        video = talk_dir / "Video" / "final"
        video.mkdir(parents=True)

        srt_old = """1
00:00:01,000 --> 00:00:03,000
Привіт.

2
00:00:04,000 --> 00:00:06,000
Як справи?

3
00:00:07,000 --> 00:00:09,000
Привіт.
"""
        (talk_dir / "uk_old.srt").write_text(srt_old, encoding="utf-8")
        # Edit only the second "Привіт"
        srt_new = """1
00:00:01,000 --> 00:00:03,000
Привіт.

2
00:00:04,000 --> 00:00:06,000
Як справи?

3
00:00:07,000 --> 00:00:09,000
Вітаю.
"""
        (video / "uk.srt").write_text(srt_new, encoding="utf-8")
        (talk_dir / "transcript_uk.txt").write_text(HEADER + "Привіт. Як справи? Привіт.\n", encoding="utf-8")

        result = sync_srt_to_transcript(
            old_srt=str(talk_dir / "uk_old.srt"),
            new_srt=str(video / "uk.srt"),
            transcript=str(talk_dir / "transcript_uk.txt"),
        )
        assert result["changed"] == 1
        text = (talk_dir / "transcript_uk.txt").read_text(encoding="utf-8")
        # The first "Привіт." stays, the second becomes "Вітаю."
        assert text.count("Привіт.") == 1
        assert "Вітаю." in text
        # Order check: Привіт comes before Вітаю
        assert text.index("Привіт.") < text.index("Вітаю.")
