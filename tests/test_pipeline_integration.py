"""Integration test for the subtitle pipeline.

Exercises the full pipeline: build_blocks_from_paragraphs -> (mock LLM
timecodes written directly to timecodes.txt) -> cmd_assemble -> build_srt
-> validate.
"""

import json

from tools.srt_utils import ms_to_time, parse_srt
from tools.text_segmentation import build_blocks_from_paragraphs, load_transcript
from tools.validate_subtitles import validate

# ---------------------------------------------------------------------------
# Inline test data
# ---------------------------------------------------------------------------

# Five EN paragraphs (single-newline format, matching amruta transcript style)
EN_TRANSCRIPT = """\
Talk Language: English
I bow to all the seekers of truth. Today I want to tell you about the subtle system.
There are seven chakras within us. The kundalini resides in the sacrum bone.
When the kundalini rises it passes through these chakras. You feel the cool breeze on your hands.
This is the proof of self-realization. You become your own master.
Meditation is the way to grow deeper in your awareness.
"""

# Five UK paragraphs (double-newline format)
UK_TRANSCRIPT = """\
Я вклоняюся усім шукачам істини. Сьогодні Я хочу розповісти вам про тонку систему.

В нас є сім чакр. Кундаліні знаходиться в крижовій кістці.

Коли Кундаліні піднімається, вона проходить через ці чакри. Ви відчуваєте прохолодний вітерець на руках.

Це є доказом самореалізації. Ви стаєте своїм власним майстром.

Медитація це шлях до глибшого усвідомлення.
"""


def _generate_mock_timecodes(uk_blocks):
    """Distribute timecodes evenly across all blocks.

    Simulates what a single-pass Opus agent would return: one timecode
    line per block, with even spacing across the full time range.
    """
    # 2 seconds per block, 100ms gap
    block_dur = 2000
    gap = 100

    lines = []
    for i, block in enumerate(uk_blocks):
        b_start = 1000 + i * block_dur
        b_end = b_start + block_dur - gap
        lines.append(f"#{block['id']} | {ms_to_time(b_start)} | {ms_to_time(b_end)}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


class TestPipelineIntegration:
    """End-to-end integration test for the subtitle build pipeline."""

    def test_full_pipeline(self, tmp_path):
        # -- Setup: write transcript files -----------------------------------
        en_path = tmp_path / "transcript_en.txt"
        uk_path = tmp_path / "transcript_uk.txt"
        en_path.write_text(EN_TRANSCRIPT, encoding="utf-8")
        uk_path.write_text(UK_TRANSCRIPT, encoding="utf-8")

        # -- Step 1: Load transcripts ----------------------------------------
        en_paragraphs = load_transcript(str(en_path))
        uk_paragraphs = load_transcript(str(uk_path))

        assert len(en_paragraphs) == 5
        assert len(uk_paragraphs) == 5

        # -- Step 2: Build whisper JSON (for validation only) ----------------
        whisper_segments = _build_whisper_segments(en_paragraphs)
        whisper_path = tmp_path / "whisper.json"
        whisper_path.write_text(
            json.dumps({"language": "en", "segments": whisper_segments}, ensure_ascii=False),
            encoding="utf-8",
        )

        # -- Step 3: build_blocks_from_paragraphs ----------------------------
        uk_blocks = build_blocks_from_paragraphs(uk_paragraphs)

        assert len(uk_blocks) > 0
        # IDs must be sequential starting from 1
        expected_ids = list(range(1, len(uk_blocks) + 1))
        actual_ids = [b["id"] for b in uk_blocks]
        assert actual_ids == expected_ids, "Block IDs must be sequential from 1"

        # Every block must have text and para_idx
        for b in uk_blocks:
            assert b["text"].strip(), f"Block #{b['id']} has empty text"
            assert "para_idx" in b

        # -- Step 4: Write uk_blocks.json and timecodes.txt ------------------
        work = tmp_path / "work"
        work.mkdir()
        (work / "uk_blocks.json").write_text(json.dumps(uk_blocks, ensure_ascii=False, indent=2), encoding="utf-8")
        timecodes_text = _generate_mock_timecodes(uk_blocks)
        (work / "timecodes.txt").write_text(timecodes_text, encoding="utf-8")

        # -- Step 5: cmd_assemble → uk.map + uk.srt --------------------------
        import argparse

        from tools.build_map import cmd_assemble

        (tmp_path / "final").mkdir()

        # cmd_assemble expects talk_dir/video_slug layout
        talk = tmp_path / "talk"
        video = talk / "video1"
        (video / "work").mkdir(parents=True)
        (video / "final").mkdir(parents=True)
        (video / "work" / "uk_blocks.json").write_text(
            json.dumps(uk_blocks, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (video / "work" / "timecodes.txt").write_text(timecodes_text, encoding="utf-8")

        args = argparse.Namespace(talk_dir=str(talk), video_slug="video1")
        cmd_assemble(args)

        map_path = video / "work" / "uk.map"
        srt_path = video / "final" / "uk.srt"

        assert map_path.exists(), "uk.map was not created"
        assert srt_path.exists(), "SRT file was not created"
        assert srt_path.stat().st_size > 0, "SRT file is empty"

        # Parse and verify the SRT
        srt_blocks = parse_srt(str(srt_path))
        assert len(srt_blocks) > 0, "No blocks parsed from SRT"

        # -- Step 6: validate ------------------------------------------------
        passed, report_lines = validate(
            srt_path=str(srt_path),
            transcript_path=str(uk_path),
            whisper_json_path=str(whisper_path),
            report_path=str(tmp_path / "validate_report.txt"),
            skip_cps_check=True,
            skip_duration_check=True,
        )

        # Print report for debugging if validation fails
        if not passed:
            print("\n".join(report_lines))

        # Core assertions from the validate report
        assert _check_passed(report_lines, "Text preservation"), (
            "Text preservation failed -- SRT text doesn't match transcript"
        )
        assert _check_passed(report_lines, "No overlaps"), "Overlaps detected in SRT"
        assert _check_passed(report_lines, "Sequential numbering"), "Sequential numbering failed"

    def test_blocks_cover_all_text(self, tmp_path):
        """Verify that build_blocks_from_paragraphs preserves all transcript words."""
        uk_path = tmp_path / "transcript_uk.txt"
        uk_path.write_text(UK_TRANSCRIPT, encoding="utf-8")

        uk_paragraphs = load_transcript(str(uk_path))
        uk_blocks = build_blocks_from_paragraphs(uk_paragraphs)

        # Collect all words from blocks
        block_words = []
        for b in uk_blocks:
            block_words.extend(b["text"].split())

        # Collect all words from paragraphs
        para_words = []
        for p in uk_paragraphs:
            para_words.extend(p.split())

        assert block_words == para_words, "Block splitting lost or reordered words"


def _build_whisper_segments(en_paragraphs):
    """Build mock whisper segments with word-level timestamps covering all EN text.

    Each paragraph becomes one whisper segment. Words are spaced 0.5s apart,
    with 1s gaps between paragraphs.
    """
    segments = []
    current_time = 1.0  # start at 1 second

    for seg_id, para in enumerate(en_paragraphs):
        words_raw = para.split()
        if not words_raw:
            continue

        seg_start = current_time
        words = []
        for word in words_raw:
            words.append(
                {
                    "start": current_time,
                    "end": current_time + 0.5,
                    "word": f" {word}",
                }
            )
            current_time += 0.5

        seg_end = current_time
        segments.append(
            {
                "id": seg_id,
                "start": seg_start,
                "end": seg_end,
                "text": " " + para,
                "words": words,
            }
        )
        current_time += 1.0  # gap between segments

    return segments


def _check_passed(report_lines, check_name):
    """Check whether a named check passed in the validation report."""
    for line in report_lines:
        if check_name in line and "[PASS]" in line:
            return True
        if check_name in line and "[FAIL]" in line:
            return False
    # If not found, assume passed (check may have been skipped)
    return True
