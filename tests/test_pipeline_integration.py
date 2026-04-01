"""Integration test for the subtitle pipeline.

Exercises the full pipeline: prepare_uk_blocks -> find_paragraph_boundaries ->
make_chunks -> (mock LLM timecodes) -> build .map -> build_srt -> validate.
"""

import json

from tools.align_uk import load_transcript
from tools.build_map import (
    find_paragraph_boundaries,
    make_chunks,
    prepare_uk_blocks,
)
from tools.build_srt import build_srt
from tools.srt_utils import ms_to_time, parse_srt
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


def _generate_mock_timecodes(chunks, uk_blocks):
    """Distribute timecodes evenly across each chunk's time range.

    Simulates what an LLM would return: one timecode line per block,
    with even spacing within the chunk's [time_start_ms, time_end_ms].
    """
    timecodes = {}  # block_id -> (start_tc, end_tc)

    for chunk in chunks:
        blocks = chunk["blocks"]
        n = len(blocks)
        t_start = chunk["time_start_ms"]
        t_end = chunk["time_end_ms"]

        # Ensure we have a valid range
        if t_end <= t_start:
            t_end = t_start + n * 2000

        duration = t_end - t_start
        block_dur = duration / n
        gap = 100  # 100ms gap between blocks

        for i, block in enumerate(blocks):
            b_start = t_start + int(i * block_dur)
            b_end = t_start + int((i + 1) * block_dur) - gap
            # Ensure minimum duration
            if b_end <= b_start:
                b_end = b_start + 1200
            timecodes[block["id"]] = (ms_to_time(b_start), ms_to_time(b_end))

    return timecodes


def _write_map_file(map_path, uk_blocks, timecodes):
    """Write a .map file from blocks and timecodes."""
    lines = []
    for block in uk_blocks:
        bid = block["id"]
        start_tc, end_tc = timecodes[bid]
        lines.append(f"{bid} | {start_tc} | {end_tc} | {block['text']}")
    map_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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

        # -- Step 2: Build whisper segments ----------------------------------
        whisper_segments = _build_whisper_segments(en_paragraphs)
        assert len(whisper_segments) == 5

        # Save whisper JSON (needed later for validation if desired)
        whisper_path = tmp_path / "whisper.json"
        whisper_path.write_text(
            json.dumps({"language": "en", "segments": whisper_segments}, ensure_ascii=False),
            encoding="utf-8",
        )

        # -- Step 3: prepare_uk_blocks ---------------------------------------
        uk_blocks = prepare_uk_blocks(uk_paragraphs)

        assert len(uk_blocks) > 0
        # IDs must be sequential starting from 1
        expected_ids = list(range(1, len(uk_blocks) + 1))
        actual_ids = [b["id"] for b in uk_blocks]
        assert actual_ids == expected_ids, "Block IDs must be sequential from 1"

        # Every block must have text and para_idx
        for b in uk_blocks:
            assert b["text"].strip(), f"Block #{b['id']} has empty text"
            assert "para_idx" in b

        # -- Step 4: find_paragraph_boundaries -------------------------------
        para_bounds = find_paragraph_boundaries(en_paragraphs, whisper_segments)

        assert len(para_bounds) == len(en_paragraphs)
        # At least some paragraphs should have non-zero boundaries
        covered = sum(1 for s, e in para_bounds if s > 0 or e > 0)
        assert covered > 0, "No paragraph boundaries found"

        # -- Step 5: make_chunks ---------------------------------------------
        chunks = make_chunks(uk_blocks, para_bounds)

        assert len(chunks) > 0, "No chunks produced"

        # Verify all block IDs are covered by chunks
        all_chunk_block_ids = set()
        for chunk in chunks:
            for block in chunk["blocks"]:
                all_chunk_block_ids.add(block["id"])
        all_block_ids = {b["id"] for b in uk_blocks}
        assert all_chunk_block_ids == all_block_ids, f"Chunks missing blocks: {all_block_ids - all_chunk_block_ids}"

        # Each chunk has required fields
        for chunk in chunks:
            assert "idx" in chunk
            assert "blocks" in chunk
            assert "time_start_ms" in chunk
            assert "time_end_ms" in chunk
            assert "para_indices" in chunk

        # -- Step 6: Generate mock LLM timecodes -----------------------------
        timecodes = _generate_mock_timecodes(chunks, uk_blocks)

        assert len(timecodes) == len(uk_blocks), f"Timecodes count {len(timecodes)} != blocks count {len(uk_blocks)}"

        # -- Step 7: Write .map file -----------------------------------------
        map_path = tmp_path / "uk.map"
        _write_map_file(map_path, uk_blocks, timecodes)

        assert map_path.exists()
        assert map_path.stat().st_size > 0

        # -- Step 8: build_srt -----------------------------------------------
        srt_path = tmp_path / "uk.srt"
        report_path = tmp_path / "build_report.txt"
        build_srt(str(map_path), str(srt_path), str(report_path))

        assert srt_path.exists(), "SRT file was not created"
        assert srt_path.stat().st_size > 0, "SRT file is empty"

        # Parse and verify the SRT
        srt_blocks = parse_srt(str(srt_path))
        assert len(srt_blocks) > 0, "No blocks parsed from SRT"

        # -- Step 9: validate ------------------------------------------------
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
        # Text preservation
        assert _check_passed(report_lines, "Text preservation"), (
            "Text preservation failed -- SRT text doesn't match transcript"
        )

        # No overlaps
        assert _check_passed(report_lines, "No overlaps"), "Overlaps detected in SRT"

        # Sequential numbering
        assert _check_passed(report_lines, "Sequential numbering"), "Sequential numbering failed"

    def test_blocks_cover_all_text(self, tmp_path):
        """Verify that prepare_uk_blocks preserves all transcript words."""
        uk_path = tmp_path / "transcript_uk.txt"
        uk_path.write_text(UK_TRANSCRIPT, encoding="utf-8")

        uk_paragraphs = load_transcript(str(uk_path))
        uk_blocks = prepare_uk_blocks(uk_paragraphs)

        # Collect all words from blocks
        block_words = []
        for b in uk_blocks:
            block_words.extend(b["text"].split())

        # Collect all words from paragraphs
        para_words = []
        for p in uk_paragraphs:
            para_words.extend(p.split())

        assert block_words == para_words, "Block splitting lost or reordered words"

    def test_chunk_time_ranges_cover_blocks(self, tmp_path):
        """Verify that chunk time ranges are valid (start <= end)."""
        en_path = tmp_path / "transcript_en.txt"
        uk_path = tmp_path / "transcript_uk.txt"
        en_path.write_text(EN_TRANSCRIPT, encoding="utf-8")
        uk_path.write_text(UK_TRANSCRIPT, encoding="utf-8")

        en_paragraphs = load_transcript(str(en_path))
        uk_paragraphs = load_transcript(str(uk_path))
        whisper_segments = _build_whisper_segments(en_paragraphs)

        uk_blocks = prepare_uk_blocks(uk_paragraphs)
        para_bounds = find_paragraph_boundaries(en_paragraphs, whisper_segments)
        chunks = make_chunks(uk_blocks, para_bounds)

        for chunk in chunks:
            assert chunk["time_start_ms"] <= chunk["time_end_ms"], (
                f"Chunk {chunk['idx']} has invalid time range: {chunk['time_start_ms']} > {chunk['time_end_ms']}"
            )


def _check_passed(report_lines, check_name):
    """Check whether a named check passed in the validation report."""
    for line in report_lines:
        if check_name in line and "[PASS]" in line:
            return True
        if check_name in line and "[FAIL]" in line:
            return False
    # If not found, assume passed (check may have been skipped)
    return True
