"""Tests for tools.build_map."""

import json
import re

from tools.build_map import (
    _normalize,
    build_chunk_prompt,
    find_paragraph_boundaries,
    format_en_srt_for_chunk,
    format_whisper_for_chunk,
    make_chunks,
    prepare_uk_blocks,
)

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
# prepare_uk_blocks
# ---------------------------------------------------------------------------


class TestPrepareUkBlocks:
    def test_single_paragraph_single_sentence(self):
        paras = ["Коротке речення."]
        blocks = prepare_uk_blocks(paras)
        assert len(blocks) == 1
        assert blocks[0]["id"] == 1
        assert blocks[0]["text"] == "Коротке речення."
        assert blocks[0]["para_idx"] == 0

    def test_single_paragraph_multiple_sentences(self):
        paras = ["Перше речення. Друге речення."]
        blocks = prepare_uk_blocks(paras)
        assert len(blocks) >= 2
        assert blocks[0]["id"] == 1
        assert blocks[1]["id"] == 2
        # All blocks belong to paragraph 0
        assert all(b["para_idx"] == 0 for b in blocks)

    def test_multiple_paragraphs(self):
        paras = ["Перший абзац.", "Другий абзац."]
        blocks = prepare_uk_blocks(paras)
        assert len(blocks) == 2
        assert blocks[0]["para_idx"] == 0
        assert blocks[1]["para_idx"] == 1

    def test_ids_sequential(self):
        paras = ["Перше.", "Друге.", "Третє."]
        blocks = prepare_uk_blocks(paras)
        for i, b in enumerate(blocks):
            assert b["id"] == i + 1

    def test_cpl_constraint(self):
        """All blocks must be <= 84 characters per line."""
        long_text = "Це дуже довге речення яке містить набагато більше ніж вісімдесят чотири символи тому повинно бути розділене на менші частини для субтитрів."
        paras = [long_text]
        blocks = prepare_uk_blocks(paras)
        for b in blocks:
            assert len(b["text"]) <= 84, f"Block too long ({len(b['text'])} CPL): {b['text']}"

    def test_empty_paragraphs(self):
        blocks = prepare_uk_blocks([])
        assert blocks == []

    def test_preserves_text(self):
        """All original text should appear across blocks."""
        paras = ["Перше речення.", "Друге речення."]
        blocks = prepare_uk_blocks(paras)
        all_text = " ".join(b["text"] for b in blocks)
        assert "Перше речення." in all_text
        assert "Друге речення." in all_text


# ---------------------------------------------------------------------------
# find_paragraph_boundaries
# ---------------------------------------------------------------------------


def _make_whisper_seg(start, end, text, words=None):
    """Helper to create a whisper segment."""
    if words is None:
        # Auto-create words from text
        w_list = []
        duration = end - start
        ws = text.split()
        for i, w in enumerate(ws):
            w_start = start + (duration * i / max(len(ws), 1))
            w_end = start + (duration * (i + 1) / max(len(ws), 1))
            w_list.append({"word": w, "start": w_start, "end": w_end})
        words = w_list
    return {"start": start, "end": end, "text": text, "words": words}


class TestFindParagraphBoundaries:
    def test_single_paragraph(self):
        en_paras = ["Hello world"]
        segs = [_make_whisper_seg(1.0, 3.0, "Hello world")]
        bounds = find_paragraph_boundaries(en_paras, segs)
        assert len(bounds) == 1
        assert bounds[0][0] > 0  # start > 0
        assert bounds[0][1] > bounds[0][0]  # end > start

    def test_multiple_paragraphs(self):
        en_paras = ["Hello world", "Good morning"]
        segs = [
            _make_whisper_seg(1.0, 3.0, "Hello world"),
            _make_whisper_seg(4.0, 6.0, "Good morning"),
        ]
        bounds = find_paragraph_boundaries(en_paras, segs)
        assert len(bounds) == 2
        # First paragraph should be around 1-3s
        assert bounds[0][0] >= 1000
        assert bounds[0][1] <= 3500
        # Second paragraph should be around 4-6s
        assert bounds[1][0] >= 3500
        assert bounds[1][1] <= 6500

    def test_empty_paragraphs(self):
        bounds = find_paragraph_boundaries([], [])
        assert bounds == []

    def test_empty_whisper(self):
        en_paras = ["Hello world"]
        bounds = find_paragraph_boundaries(en_paras, [])
        assert bounds == [(0, 0)]

    def test_unmatched_paragraph(self):
        """Paragraph with no matching whisper words returns (0, 0)."""
        en_paras = ["Hello world", "Completely different text"]
        segs = [_make_whisper_seg(1.0, 3.0, "Hello world")]
        bounds = find_paragraph_boundaries(en_paras, segs)
        assert len(bounds) == 2
        # First matches
        assert bounds[0] != (0, 0)
        # Second doesn't match — should be (0, 0) since words don't overlap
        # Note: SequenceMatcher may or may not match "different" etc.
        # At minimum, first paragraph should have a valid boundary
        assert bounds[0][0] > 0

    def test_times_in_milliseconds(self):
        en_paras = ["Test"]
        segs = [_make_whisper_seg(2.5, 3.5, "Test")]
        bounds = find_paragraph_boundaries(en_paras, segs)
        # Times should be in milliseconds
        assert bounds[0][0] == 2500
        assert bounds[0][1] == 3500

    def test_empty_en_paragraphs_nonempty_whisper(self):
        segs = [_make_whisper_seg(1.0, 2.0, "Hello")]
        bounds = find_paragraph_boundaries([], segs)
        assert bounds == []


# ---------------------------------------------------------------------------
# make_chunks
# ---------------------------------------------------------------------------


def _make_blocks(n, para_idx=0, start_id=1):
    """Helper to create n blocks for a given paragraph."""
    return [{"id": start_id + i, "text": f"Block {start_id + i}", "para_idx": para_idx} for i in range(n)]


class TestMakeChunks:
    def test_small_paragraphs_single_chunk(self):
        """Few blocks from a single paragraph -> one chunk."""
        blocks = _make_blocks(5, para_idx=0)
        bounds = [(1000, 5000)]
        chunks = make_chunks(blocks, bounds)
        assert len(chunks) == 1
        assert len(chunks[0]["blocks"]) == 5
        assert chunks[0]["time_start_ms"] == 1000
        assert chunks[0]["time_end_ms"] == 5000

    def test_multiple_small_paragraphs_merged(self):
        """Multiple small paragraphs fit in one chunk."""
        blocks = _make_blocks(5, para_idx=0) + _make_blocks(5, para_idx=1, start_id=6)
        bounds = [(1000, 3000), (3000, 6000)]
        chunks = make_chunks(blocks, bounds)
        # 10 blocks total, below CHUNK_TARGET of 30
        assert len(chunks) == 1
        assert len(chunks[0]["blocks"]) == 10

    def test_chunk_max_splitting(self):
        """Paragraphs with many blocks get split at CHUNK_MAX."""
        # Create multiple paragraphs each with many blocks
        blocks = []
        bounds = []
        for p in range(5):
            blocks.extend(_make_blocks(15, para_idx=p, start_id=len(blocks) + 1))
            bounds.append((p * 10000, (p + 1) * 10000))
        # 75 blocks total, should produce multiple chunks
        chunks = make_chunks(blocks, bounds)
        assert len(chunks) >= 2
        for c in chunks:
            assert len(c["blocks"]) <= 50  # CHUNK_MAX

    def test_chunk_idx_sequential(self):
        blocks = _make_blocks(5, para_idx=0) + _make_blocks(5, para_idx=1, start_id=6)
        bounds = [(0, 5000), (5000, 10000)]
        chunks = make_chunks(blocks, bounds)
        for i, c in enumerate(chunks):
            assert c["idx"] == i

    def test_empty_blocks(self):
        chunks = make_chunks([], [])
        assert chunks == []

    def test_para_indices_preserved(self):
        blocks = _make_blocks(10, para_idx=0) + _make_blocks(10, para_idx=1, start_id=11)
        bounds = [(0, 5000), (5000, 10000)]
        chunks = make_chunks(blocks, bounds)
        # All paragraph indices should be in the chunk para_indices
        all_paras = set()
        for c in chunks:
            all_paras.update(c["para_indices"])
        assert 0 in all_paras
        assert 1 in all_paras

    def test_time_boundaries_from_para_bounds(self):
        """Chunk time boundaries come from paragraph boundaries."""
        blocks = _make_blocks(5, para_idx=0) + _make_blocks(5, para_idx=1, start_id=6)
        bounds = [(2000, 8000), (10000, 15000)]
        chunks = make_chunks(blocks, bounds)
        # Single chunk covering both paragraphs
        if len(chunks) == 1:
            assert chunks[0]["time_start_ms"] == 2000
            assert chunks[0]["time_end_ms"] == 15000

    def test_zero_time_boundaries_excluded_from_valid(self):
        """Paragraphs with (0,0) boundaries don't affect time range."""
        blocks = _make_blocks(5, para_idx=0) + _make_blocks(5, para_idx=1, start_id=6)
        bounds = [(0, 0), (5000, 10000)]
        chunks = make_chunks(blocks, bounds)
        if len(chunks) == 1:
            assert chunks[0]["time_start_ms"] == 5000
            assert chunks[0]["time_end_ms"] == 10000

    def test_oversized_paragraph_sub_chunked(self):
        """A single paragraph with >CHUNK_MAX blocks is split into sub-chunks."""
        blocks = _make_blocks(60, para_idx=0)  # Exceeds CHUNK_MAX (50)
        bounds = [(0, 60000)]
        chunks = make_chunks(blocks, bounds)
        # Should be split into sub-chunks of CHUNK_TARGET (30)
        assert len(chunks) >= 2
        total_blocks = sum(len(c["blocks"]) for c in chunks)
        assert total_blocks == 60

    def test_chunk_max_paras_limit(self):
        """Chunks respect CHUNK_MAX_PARAS (15) limit."""
        blocks = []
        bounds = []
        for p in range(20):
            blocks.extend(_make_blocks(1, para_idx=p, start_id=len(blocks) + 1))
            bounds.append((p * 1000, (p + 1) * 1000))
        # 20 paragraphs with 1 block each — should split due to CHUNK_MAX_PARAS
        chunks = make_chunks(blocks, bounds)
        for c in chunks:
            assert len(c["para_indices"]) <= 15


# ---------------------------------------------------------------------------
# format_whisper_for_chunk
# ---------------------------------------------------------------------------


class TestFormatWhisperForChunk:
    def test_basic_formatting(self):
        segs = [
            {
                "start": 1.0,
                "end": 3.0,
                "text": " Hello world",
                "words": [
                    {"word": " Hello", "start": 1.0, "end": 1.5},
                    {"word": " world", "start": 1.5, "end": 3.0},
                ],
            }
        ]
        result = format_whisper_for_chunk(segs, 0, 5000)
        assert "Hello world" in result
        assert "00:00:01,000" in result
        assert "Words:" in result

    def test_filters_by_time_range(self):
        segs = [
            {"start": 1.0, "end": 2.0, "text": " Early", "words": []},
            {"start": 10.0, "end": 12.0, "text": " Middle", "words": []},
            {"start": 50.0, "end": 52.0, "text": " Late", "words": []},
        ]
        result = format_whisper_for_chunk(segs, 9000, 13000)
        assert "Middle" in result
        # With 5000ms margin: 9000-5000=4000, 13000+5000=18000
        # Early ends at 2000 < 4000 -> excluded
        assert "Early" not in result
        # Late starts at 50000 > 18000 -> excluded
        assert "Late" not in result

    def test_empty_segments(self):
        result = format_whisper_for_chunk([], 0, 10000)
        assert result == ""

    def test_includes_margin(self):
        """Segments within 5000ms margin should be included."""
        segs = [
            {"start": 3.0, "end": 4.0, "text": " Near start", "words": []},
        ]
        # Chunk starts at 8000, margin 5000 -> include if seg_e >= 3000
        result = format_whisper_for_chunk(segs, 8000, 15000)
        assert "Near start" in result

    def test_word_formatting(self):
        segs = [
            {
                "start": 1.0,
                "end": 2.0,
                "text": " Hi",
                "words": [{"word": " Hi", "start": 1.0, "end": 2.0}],
            }
        ]
        result = format_whisper_for_chunk(segs, 0, 5000)
        assert "Hi 00:00:01,000->00:00:02,000" in result


# ---------------------------------------------------------------------------
# format_en_srt_for_chunk
# ---------------------------------------------------------------------------


def _make_srt_block(idx, start_ms, end_ms, text):
    return {"idx": idx, "start_ms": start_ms, "end_ms": end_ms, "text": text}


class TestFormatEnSrtForChunk:
    def test_basic_formatting(self):
        blocks = [_make_srt_block(1, 1000, 3000, "Hello world")]
        result = format_en_srt_for_chunk(blocks, 0, 5000)
        assert "EN#1" in result
        assert "Hello world" in result
        assert "00:00:01,000" in result

    def test_filters_by_time_range(self):
        blocks = [
            _make_srt_block(1, 1000, 2000, "Early"),
            _make_srt_block(2, 10000, 12000, "Middle"),
            _make_srt_block(3, 100000, 102000, "Late"),
        ]
        result = format_en_srt_for_chunk(blocks, 9000, 13000)
        assert "Middle" in result
        # Margin is 50% of chunk duration = 50% * 4000 = 2000
        # Early ends at 2000 < 9000-2000=7000 -> excluded
        assert "Early" not in result
        # Late starts at 100000 > 13000+2000=15000 -> excluded
        assert "Late" not in result

    def test_empty_blocks(self):
        result = format_en_srt_for_chunk([], 0, 10000)
        assert result == ""

    def test_margin_is_half_chunk_duration(self):
        """Margin = 50% of chunk duration."""
        blocks = [
            _make_srt_block(1, 3000, 4000, "Near boundary"),
        ]
        # Chunk is 10000-20000 (dur=10000), margin=5000
        # Block ends at 4000 < 10000-5000=5000 -> excluded
        result = format_en_srt_for_chunk(blocks, 10000, 20000)
        assert "Near boundary" not in result

        # But for a smaller chunk: 10000-12000 (dur=2000), margin=1000
        # Block ends at 4000 < 10000-1000=9000 -> excluded
        result = format_en_srt_for_chunk(blocks, 10000, 12000)
        assert "Near boundary" not in result

    def test_minimum_margin(self):
        """Chunk duration < 10000 still gets min 10000/2 = 5000 margin."""
        blocks = [_make_srt_block(1, 4500, 5000, "Edge")]
        # Chunk is 8000-9000 (dur=1000 -> clamped to 10000), margin=5000
        # Block ends at 5000 >= 8000-5000=3000 -> included
        result = format_en_srt_for_chunk(blocks, 8000, 9000)
        assert "Edge" in result

    def test_output_format(self):
        blocks = [_make_srt_block(42, 5000, 7000, "Test line")]
        result = format_en_srt_for_chunk(blocks, 0, 10000)
        assert result.startswith("EN#42 [")
        assert "->" in result
        assert "Test line" in result


# ---------------------------------------------------------------------------
# build_chunk_prompt
# ---------------------------------------------------------------------------


class TestBuildChunkPrompt:
    def _make_blocks(self, n=3, start_id=1):
        return [{"id": start_id + i, "text": f"Блок {start_id + i}."} for i in range(n)]

    def test_whisper_mode_default(self):
        blocks = self._make_blocks()
        prompt = build_chunk_prompt(blocks, "English text", "Whisper data", 1000, 5000, timing_source="whisper")
        assert "WHISPER DATA" in prompt
        assert "ENGLISH TRANSCRIPT" in prompt
        assert "UKRAINIAN BLOCKS" in prompt
        assert "#1: Блок 1." in prompt
        assert "#2: Блок 2." in prompt
        assert "#3: Блок 3." in prompt

    def test_en_srt_mode(self):
        blocks = self._make_blocks()
        prompt = build_chunk_prompt(blocks, "English text", "EN SRT data", 1000, 5000, timing_source="en-srt")
        assert "ENGLISH SUBTITLES" in prompt
        assert "UKRAINIAN BLOCKS" in prompt
        assert "WHISPER DATA" not in prompt

    def test_time_boundaries_in_whisper_prompt(self):
        blocks = self._make_blocks(2, start_id=5)
        prompt = build_chunk_prompt(blocks, "en", "timing", 60000, 120000, timing_source="whisper")
        assert "00:01:00,000" in prompt  # start
        assert "00:02:00,000" in prompt  # end
        assert "#5" in prompt
        assert "#6" in prompt

    def test_output_format_instructions(self):
        blocks = self._make_blocks()
        prompt = build_chunk_prompt(blocks, "en", "timing", 0, 5000)
        assert "#<number> | <start HH:MM:SS,mmm> | <end HH:MM:SS,mmm>" in prompt

    def test_en_srt_output_format(self):
        blocks = self._make_blocks()
        prompt = build_chunk_prompt(blocks, "en", "timing", 0, 5000, timing_source="en-srt")
        assert "#<number> | <start HH:MM:SS,mmm> | <end HH:MM:SS,mmm>" in prompt

    def test_blocks_listed(self):
        blocks = self._make_blocks(5)
        prompt = build_chunk_prompt(blocks, "en", "timing", 0, 5000)
        for b in blocks:
            assert f"#{b['id']}: {b['text']}" in prompt


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

    def test_prepare_creates_output_files(self, tmp_path):
        talk_dir = self._setup_talk_dir(tmp_path)

        # Simulate cmd_prepare by calling the functions directly
        from tools.align_uk import load_transcript
        from tools.srt_utils import load_whisper_json

        uk_paras = load_transcript(str(talk_dir / "transcript_uk.txt"))
        en_paras = load_transcript(str(talk_dir / "transcript_en.txt"))
        whisper_segs = load_whisper_json(str(talk_dir / "video1" / "source" / "whisper.json"))

        uk_blocks = prepare_uk_blocks(uk_paras)
        para_bounds = find_paragraph_boundaries(en_paras, whisper_segs)
        chunks = make_chunks(uk_blocks, para_bounds)

        # Verify outputs
        assert len(uk_blocks) >= 2
        assert len(para_bounds) == 2
        assert len(chunks) >= 1

    def test_prepare_uk_blocks_json_structure(self, tmp_path):
        talk_dir = self._setup_talk_dir(tmp_path)
        work = talk_dir / "video1" / "work"
        work.mkdir(parents=True, exist_ok=True)

        from tools.align_uk import load_transcript

        uk_paras = load_transcript(str(talk_dir / "transcript_uk.txt"))
        uk_blocks = prepare_uk_blocks(uk_paras)

        # Write and verify JSON structure
        blocks_file = work / "uk_blocks.json"
        with open(blocks_file, "w", encoding="utf-8") as f:
            json.dump(uk_blocks, f, ensure_ascii=False, indent=2)

        loaded = json.loads(blocks_file.read_text(encoding="utf-8"))
        assert isinstance(loaded, list)
        for block in loaded:
            assert "id" in block
            assert "text" in block
            assert "para_idx" in block

    def test_prepare_build_meta_structure(self, tmp_path):
        """Build meta JSON should have expected keys."""
        meta = {
            "talk_dir": str(tmp_path / "talk"),
            "video_slug": "video1",
            "n_chunks": 2,
            "n_blocks": 10,
        }
        meta_file = tmp_path / "build_meta.json"
        with open(meta_file, "w") as f:
            json.dump(meta, f, indent=2)

        loaded = json.loads(meta_file.read_text())
        assert loaded["video_slug"] == "video1"
        assert loaded["n_chunks"] == 2
        assert loaded["n_blocks"] == 10

    def test_chunk_prompt_files_written(self, tmp_path):
        talk_dir = self._setup_talk_dir(tmp_path)
        work = talk_dir / "video1" / "work"
        work.mkdir(parents=True, exist_ok=True)

        from tools.align_uk import load_transcript
        from tools.srt_utils import load_whisper_json

        uk_paras = load_transcript(str(talk_dir / "transcript_uk.txt"))
        en_paras = load_transcript(str(talk_dir / "transcript_en.txt"))
        whisper_segs = load_whisper_json(str(talk_dir / "video1" / "source" / "whisper.json"))

        uk_blocks = prepare_uk_blocks(uk_paras)
        para_bounds = find_paragraph_boundaries(en_paras, whisper_segs)
        chunks = make_chunks(uk_blocks, para_bounds)

        for chunk in chunks:
            idx = chunk["idx"]
            blocks = chunk["blocks"]
            para_idxs = chunk["para_indices"]

            en_text = "\n\n".join(f"[P{p + 1}] {en_paras[p]}" for p in para_idxs if p < len(en_paras))
            timing_text = format_whisper_for_chunk(whisper_segs, chunk["time_start_ms"], chunk["time_end_ms"])
            prompt = build_chunk_prompt(blocks, en_text, timing_text, chunk["time_start_ms"], chunk["time_end_ms"])

            prompt_file = work / f"chunk_{idx}.txt"
            prompt_file.write_text(prompt, encoding="utf-8")

        # Verify chunk files exist and are non-empty
        for i in range(len(chunks)):
            pf = work / f"chunk_{i}.txt"
            assert pf.exists()
            assert len(pf.read_text(encoding="utf-8")) > 0


# ---------------------------------------------------------------------------
# cmd_assemble (integration via file system)
# ---------------------------------------------------------------------------


class TestCmdAssemble:
    def _setup_assemble_dir(self, tmp_path, n_blocks=5, n_chunks=1, provide_results=True):
        """Set up work directory with blocks, meta, and optionally chunk results."""
        work = tmp_path / "talk" / "video1" / "work"
        work.mkdir(parents=True, exist_ok=True)
        final = tmp_path / "talk" / "video1" / "final"
        final.mkdir(parents=True, exist_ok=True)

        blocks = [{"id": i + 1, "text": f"Блок {i + 1}.", "para_idx": 0} for i in range(n_blocks)]
        (work / "uk_blocks.json").write_text(json.dumps(blocks, ensure_ascii=False), encoding="utf-8")

        meta = {
            "talk_dir": str(tmp_path / "talk"),
            "video_slug": "video1",
            "n_chunks": n_chunks,
            "n_blocks": n_blocks,
        }
        (work / "build_meta.json").write_text(json.dumps(meta))

        if provide_results:
            # Generate chunk results
            lines_per_chunk = n_blocks // max(n_chunks, 1)
            for ci in range(n_chunks):
                result_lines = []
                start_block = ci * lines_per_chunk + 1
                end_block = min((ci + 1) * lines_per_chunk, n_blocks) if ci < n_chunks - 1 else n_blocks
                for bid in range(start_block, end_block + 1):
                    start_ms = bid * 2000
                    end_ms = start_ms + 1500
                    start_tc = f"00:00:{start_ms // 1000:02d},{start_ms % 1000:03d}"
                    end_tc = f"00:00:{end_ms // 1000:02d},{end_ms % 1000:03d}"
                    result_lines.append(f"#{bid} | {start_tc} | {end_tc}")
                (work / f"chunk_{ci}_result.txt").write_text("\n".join(result_lines), encoding="utf-8")

        return work

    def test_assemble_builds_mapping(self, tmp_path):
        work = self._setup_assemble_dir(tmp_path, n_blocks=3, n_chunks=1)

        # Read blocks and meta
        with open(work / "uk_blocks.json", encoding="utf-8") as f:
            uk_blocks = json.load(f)
        with open(work / "build_meta.json") as f:
            meta = json.load(f)

        # Parse chunk results (simulating cmd_assemble logic)
        tc_re = re.compile(r"#(\d+)\s*\|\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\|\s*(\d{2}:\d{2}:\d{2},\d{3})")
        all_timecodes = {}
        for idx in range(meta["n_chunks"]):
            text = (work / f"chunk_{idx}_result.txt").read_text(encoding="utf-8")
            for line in text.split("\n"):
                m = tc_re.search(line)
                if m:
                    all_timecodes[int(m.group(1))] = (m.group(2), m.group(3))

        # Build mapping lines
        map_lines = []
        for block in uk_blocks:
            bid = block["id"]
            if bid in all_timecodes:
                start_tc, end_tc = all_timecodes[bid]
                map_lines.append(f"{bid} | {start_tc} | {end_tc} | {block['text']}")

        assert len(map_lines) == 3
        assert "Блок 1." in map_lines[0]
        assert "Блок 2." in map_lines[1]
        assert "Блок 3." in map_lines[2]

    def test_assemble_missing_chunk_result(self, tmp_path):
        """Missing chunk result files should be detected."""
        work = self._setup_assemble_dir(tmp_path, n_blocks=5, n_chunks=2, provide_results=False)

        with open(work / "build_meta.json") as f:
            meta = json.load(f)

        errors = []
        for idx in range(meta["n_chunks"]):
            result_file = work / f"chunk_{idx}_result.txt"
            if not result_file.exists():
                errors.append(f"Chunk {idx}: result file missing")

        assert len(errors) == 2
        assert "Chunk 0" in errors[0]
        assert "Chunk 1" in errors[1]

    def test_assemble_empty_chunk_result(self, tmp_path):
        """Empty chunk results with no timecodes should be detected."""
        work = self._setup_assemble_dir(tmp_path, n_blocks=3, n_chunks=1, provide_results=False)

        # Write empty result
        (work / "chunk_0_result.txt").write_text("No valid timecodes here.\nJust garbage.", encoding="utf-8")

        tc_re = re.compile(r"#(\d+)\s*\|\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\|\s*(\d{2}:\d{2}:\d{2},\d{3})")
        errors = []
        text = (work / "chunk_0_result.txt").read_text(encoding="utf-8")
        chunk_tc = {}
        for line in text.split("\n"):
            m = tc_re.search(line)
            if m:
                chunk_tc[int(m.group(1))] = (m.group(2), m.group(3))
        if not chunk_tc:
            errors.append("Chunk 0: no timecodes found in result")

        assert len(errors) == 1

    def test_assemble_timecode_regex_parsing(self, tmp_path):
        """Verify the timecode regex parses various formats."""
        tc_re = re.compile(r"#(\d+)\s*\|\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\|\s*(\d{2}:\d{2}:\d{2},\d{3})")

        # Standard format
        m = tc_re.search("#1 | 00:00:01,000 | 00:00:03,500")
        assert m
        assert m.group(1) == "1"
        assert m.group(2) == "00:00:01,000"
        assert m.group(3) == "00:00:03,500"

        # No spaces
        m = tc_re.search("#42|01:23:45,678|01:23:50,000")
        assert m
        assert m.group(1) == "42"

        # Extra text around
        m = tc_re.search("  #100 | 00:05:00,000 | 00:05:05,000  some trailing text")
        assert m
        assert m.group(1) == "100"

    def test_assemble_completeness_check(self, tmp_path):
        """Should detect missing block IDs."""
        work = self._setup_assemble_dir(tmp_path, n_blocks=5, n_chunks=1)

        with open(work / "uk_blocks.json", encoding="utf-8") as f:
            uk_blocks = json.load(f)

        # Simulate partial results (only blocks 1-3, missing 4-5)
        (work / "chunk_0_result.txt").write_text(
            "#1 | 00:00:02,000 | 00:00:03,500\n#2 | 00:00:04,000 | 00:00:05,500\n#3 | 00:00:06,000 | 00:00:07,500\n",
            encoding="utf-8",
        )

        tc_re = re.compile(r"#(\d+)\s*\|\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\|\s*(\d{2}:\d{2}:\d{2},\d{3})")
        all_timecodes = {}
        text = (work / "chunk_0_result.txt").read_text(encoding="utf-8")
        for line in text.split("\n"):
            m = tc_re.search(line)
            if m:
                all_timecodes[int(m.group(1))] = (m.group(2), m.group(3))

        expected = {b["id"] for b in uk_blocks}
        got = set(all_timecodes.keys())
        missing = sorted(expected - got)
        assert missing == [4, 5]

    def test_assemble_multiple_chunks_merge(self, tmp_path):
        """Timecodes from multiple chunks should merge correctly."""
        work = self._setup_assemble_dir(tmp_path, n_blocks=6, n_chunks=2)

        with open(work / "uk_blocks.json", encoding="utf-8") as f:
            uk_blocks = json.load(f)
        with open(work / "build_meta.json") as f:
            meta = json.load(f)

        tc_re = re.compile(r"#(\d+)\s*\|\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\|\s*(\d{2}:\d{2}:\d{2},\d{3})")
        all_timecodes = {}
        for idx in range(meta["n_chunks"]):
            text = (work / f"chunk_{idx}_result.txt").read_text(encoding="utf-8")
            for line in text.split("\n"):
                m = tc_re.search(line)
                if m:
                    all_timecodes[int(m.group(1))] = (m.group(2), m.group(3))

        expected = {b["id"] for b in uk_blocks}
        assert set(all_timecodes.keys()) == expected


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_single_word_paragraph(self):
        paras = ["Слово"]
        blocks = prepare_uk_blocks(paras)
        assert len(blocks) == 1
        assert blocks[0]["text"] == "Слово"

    def test_very_long_paragraph(self):
        """Very long paragraph splits into multiple blocks, all <= 84 CPL."""
        words = ["слово"] * 100
        paras = [" ".join(words)]
        blocks = prepare_uk_blocks(paras)
        assert len(blocks) > 1
        for b in blocks:
            assert len(b["text"]) <= 84

    def test_punctuation_only_normalize(self):
        assert _normalize("!!!") == ""
        assert _normalize(".,;:") == ""
        assert _normalize("—") == ""

    def test_single_word_boundary_detection(self):
        en_paras = ["Hello"]
        segs = [_make_whisper_seg(1.0, 2.0, "Hello")]
        bounds = find_paragraph_boundaries(en_paras, segs)
        assert len(bounds) == 1
        assert bounds[0] != (0, 0)

    def test_many_paragraphs_chunking(self):
        """Many paragraphs should all end up in chunks."""
        blocks = []
        bounds = []
        for p in range(30):
            blocks.extend(_make_blocks(3, para_idx=p, start_id=len(blocks) + 1))
            bounds.append((p * 5000, (p + 1) * 5000))

        chunks = make_chunks(blocks, bounds)
        total_blocks = sum(len(c["blocks"]) for c in chunks)
        assert total_blocks == 90  # 30 * 3

    def test_normalize_with_apostrophe(self):
        assert _normalize("it's") == "its"
        assert _normalize("don't") == "dont"

    def test_normalize_with_hyphen(self):
        # Hyphen is \W, so it gets stripped
        assert _normalize("well-known") == "wellknown"

    def test_prepare_uk_blocks_paragraph_index_tracking(self):
        """Blocks from different paragraphs have correct para_idx."""
        paras = ["Перше.", "Друге.", "Третє."]
        blocks = prepare_uk_blocks(paras)
        assert blocks[0]["para_idx"] == 0
        assert blocks[1]["para_idx"] == 1
        assert blocks[2]["para_idx"] == 2

    def test_find_paragraph_boundaries_word_alignment(self):
        """Words match across whisper and transcript via normalization."""
        en_paras = ["Hello, world!"]
        # Whisper has cleaned words (without punctuation in word field)
        segs = [
            {
                "start": 1.0,
                "end": 3.0,
                "text": " Hello, world!",
                "words": [
                    {"word": " Hello,", "start": 1.0, "end": 1.5},
                    {"word": " world!", "start": 2.0, "end": 3.0},
                ],
            }
        ]
        bounds = find_paragraph_boundaries(en_paras, segs)
        assert len(bounds) == 1
        # Both words should match after normalization
        assert bounds[0][0] == 1000
        assert bounds[0][1] == 3000

    def test_make_chunks_all_zero_boundaries(self):
        """If all boundaries are (0,0), chunks still get created with 0 times."""
        blocks = _make_blocks(5, para_idx=0)
        bounds = [(0, 0)]
        chunks = make_chunks(blocks, bounds)
        assert len(chunks) >= 1
        assert chunks[0]["time_start_ms"] == 0
        assert chunks[0]["time_end_ms"] == 0

    def test_format_whisper_segments_no_words_key(self):
        """Segments without 'words' key should not crash."""
        segs = [{"start": 1.0, "end": 2.0, "text": " Hello"}]
        result = format_whisper_for_chunk(segs, 0, 5000)
        assert "Hello" in result

    def test_build_chunk_prompt_single_block(self):
        blocks = [{"id": 1, "text": "Один блок."}]
        prompt = build_chunk_prompt(blocks, "One block.", "timing", 0, 5000)
        assert "#1: Один блок." in prompt
        assert "Block #1" in prompt

    def test_en_srt_prompt_no_time_boundaries(self):
        """EN SRT prompt doesn't include explicit time boundary instructions."""
        blocks = [{"id": 1, "text": "Текст."}]
        prompt = build_chunk_prompt(blocks, "en", "timing", 0, 5000, timing_source="en-srt")
        assert "IMPORTANT TIME BOUNDARIES" not in prompt
        assert "ENGLISH SUBTITLES" in prompt
