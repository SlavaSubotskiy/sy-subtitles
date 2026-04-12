"""Tests for offset_srt.py — detect and apply time offsets between SRT files."""

from tools.offset_srt import apply_offset, detect_offset, normalize_text, text_similarity
from tools.srt_utils import parse_srt


def _write_srt(path, blocks):
    """Helper: write a list of (start_ms, end_ms, text) tuples as an SRT file."""
    lines = []
    for i, (start_ms, end_ms, text) in enumerate(blocks, 1):

        def _fmt(ms):
            h = ms // 3600000
            ms %= 3600000
            m = ms // 60000
            ms %= 60000
            s = ms // 1000
            ms %= 1000
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        lines.append(str(i))
        lines.append(f"{_fmt(start_ms)} --> {_fmt(end_ms)}")
        lines.append(text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


class TestNormalizeText:
    def test_lowercase_and_collapse_whitespace(self):
        assert normalize_text("  Hello   World  ") == "hello world"

    def test_newlines_collapsed(self):
        assert normalize_text("Line\n  One\n\nTwo") == "line one two"

    def test_empty(self):
        assert normalize_text("") == ""


class TestTextSimilarity:
    def test_identical(self):
        assert text_similarity("hello", "hello") == 1.0

    def test_completely_different(self):
        assert text_similarity("aaa", "zzz") < 0.5

    def test_similar(self):
        ratio = text_similarity("hello world", "hello worl")
        assert 0.9 < ratio < 1.0


# ---------------------------------------------------------------------------
# detect_offset tests
# ---------------------------------------------------------------------------


class TestDetectOffset:
    def test_positive_offset(self, tmp_path):
        """SRT2 starts 2000ms later than SRT1 -- detect positive offset."""
        srt1 = tmp_path / "srt1.srt"
        srt2 = tmp_path / "srt2.srt"

        blocks1 = [
            (1000, 5000, "First block."),
            (6000, 10000, "Second block."),
            (11000, 15000, "Third block."),
        ]
        blocks2 = [
            (3000, 7000, "First block."),
            (8000, 12000, "Second block."),
            (13000, 17000, "Third block."),
        ]
        _write_srt(srt1, blocks1)
        _write_srt(srt2, blocks2)

        offset = detect_offset(str(srt1), str(srt2))
        assert offset == 2000

    def test_negative_offset(self, tmp_path):
        """SRT2 starts 1500ms earlier than SRT1 -- detect negative offset."""
        srt1 = tmp_path / "srt1.srt"
        srt2 = tmp_path / "srt2.srt"

        blocks1 = [
            (5000, 8000, "Hello there."),
            (9000, 12000, "Goodbye now."),
        ]
        blocks2 = [
            (3500, 6500, "Hello there."),
            (7500, 10500, "Goodbye now."),
        ]
        _write_srt(srt1, blocks1)
        _write_srt(srt2, blocks2)

        offset = detect_offset(str(srt1), str(srt2))
        assert offset == -1500

    def test_zero_offset(self, tmp_path):
        """Identical timing -- offset should be 0."""
        srt1 = tmp_path / "srt1.srt"
        srt2 = tmp_path / "srt2.srt"

        blocks = [
            (1000, 3000, "Same timing."),
            (4000, 6000, "Exactly same."),
        ]
        _write_srt(srt1, blocks)
        _write_srt(srt2, blocks)

        offset = detect_offset(str(srt1), str(srt2))
        assert offset == 0

    def test_large_positive_offset(self, tmp_path):
        """Large offset (60 seconds) is detected correctly."""
        srt1 = tmp_path / "srt1.srt"
        srt2 = tmp_path / "srt2.srt"

        blocks1 = [
            (0, 2000, "Start."),
            (3000, 5000, "Continue."),
        ]
        blocks2 = [
            (60000, 62000, "Start."),
            (63000, 65000, "Continue."),
        ]
        _write_srt(srt1, blocks1)
        _write_srt(srt2, blocks2)

        offset = detect_offset(str(srt1), str(srt2))
        assert offset == 60000

    def test_different_block_count_returns_none(self, tmp_path):
        """When block counts differ, detect should return None."""
        srt1 = tmp_path / "srt1.srt"
        srt2 = tmp_path / "srt2.srt"

        _write_srt(srt1, [(1000, 3000, "One."), (4000, 6000, "Two.")])
        _write_srt(srt2, [(1000, 3000, "One.")])

        offset = detect_offset(str(srt1), str(srt2))
        assert offset is None

    def test_different_text_returns_none(self, tmp_path):
        """When texts are substantially different, detect should return None."""
        srt1 = tmp_path / "srt1.srt"
        srt2 = tmp_path / "srt2.srt"

        _write_srt(srt1, [(1000, 3000, "Completely different text here.")])
        _write_srt(srt2, [(2000, 4000, "Totally unrelated words now.")])

        offset = detect_offset(str(srt1), str(srt2))
        assert offset is None

    def test_inconsistent_offset_returns_none(self, tmp_path):
        """When individual block offsets vary beyond tolerance, returns None."""
        srt1 = tmp_path / "srt1.srt"
        srt2 = tmp_path / "srt2.srt"

        # Same text, but offset differs per block beyond tolerance (500ms default)
        _write_srt(
            srt1,
            [
                (1000, 3000, "Block one."),
                (4000, 6000, "Block two."),
                (7000, 9000, "Block three."),
            ],
        )
        _write_srt(
            srt2,
            [
                (3000, 5000, "Block one."),  # +2000ms
                (7000, 9000, "Block two."),  # +3000ms (differs by 1000 > 500 tolerance)
                (9000, 11000, "Block three."),  # +2000ms
            ],
        )

        offset = detect_offset(str(srt1), str(srt2))
        assert offset is None

    def test_empty_srt1_returns_none(self, tmp_path):
        """Empty first SRT file -- returns None."""
        srt1 = tmp_path / "srt1.srt"
        srt2 = tmp_path / "srt2.srt"

        srt1.write_text("", encoding="utf-8")
        _write_srt(srt2, [(1000, 3000, "Some text.")])

        offset = detect_offset(str(srt1), str(srt2))
        assert offset is None

    def test_empty_srt2_returns_none(self, tmp_path):
        """Empty second SRT file -- returns None."""
        srt1 = tmp_path / "srt1.srt"
        srt2 = tmp_path / "srt2.srt"

        _write_srt(srt1, [(1000, 3000, "Some text.")])
        srt2.write_text("", encoding="utf-8")

        offset = detect_offset(str(srt1), str(srt2))
        assert offset is None

    def test_both_empty_returns_none(self, tmp_path):
        """Both SRT files empty -- returns None."""
        srt1 = tmp_path / "srt1.srt"
        srt2 = tmp_path / "srt2.srt"

        srt1.write_text("", encoding="utf-8")
        srt2.write_text("", encoding="utf-8")

        offset = detect_offset(str(srt1), str(srt2))
        assert offset is None

    def test_single_block(self, tmp_path):
        """Single block in each file -- offset detected from that one block."""
        srt1 = tmp_path / "srt1.srt"
        srt2 = tmp_path / "srt2.srt"

        _write_srt(srt1, [(1000, 4000, "Only block.")])
        _write_srt(srt2, [(5500, 8500, "Only block.")])

        offset = detect_offset(str(srt1), str(srt2))
        assert offset == 4500

    def test_minor_text_difference_within_threshold(self, tmp_path):
        """Very small text difference (typo) should still pass if within similarity threshold."""
        srt1 = tmp_path / "srt1.srt"
        srt2 = tmp_path / "srt2.srt"

        # Long enough text so a tiny difference stays above 0.98 similarity
        long_text = "This is a very long subtitle block with many words to ensure high similarity ratio."
        slightly_different = "This is a very long subtitle block with many words to ensure high similarity ratios."

        _write_srt(
            srt1,
            [
                (1000, 5000, long_text),
                (6000, 10000, "Second block remains identical."),
            ],
        )
        _write_srt(
            srt2,
            [
                (3000, 7000, slightly_different),
                (8000, 12000, "Second block remains identical."),
            ],
        )

        offset = detect_offset(str(srt1), str(srt2))
        assert offset == 2000

    def test_custom_parameters(self, tmp_path):
        """Custom tolerance and similarity threshold work correctly."""
        srt1 = tmp_path / "srt1.srt"
        srt2 = tmp_path / "srt2.srt"

        _write_srt(
            srt1,
            [
                (1000, 3000, "Block one."),
                (4000, 6000, "Block two."),
            ],
        )
        # Block offsets differ by 800ms (would fail with default 500ms tolerance)
        _write_srt(
            srt2,
            [
                (3000, 5000, "Block one."),  # +2000ms
                (6800, 8800, "Block two."),  # +2800ms
            ],
        )

        # Should fail with default tolerance
        assert detect_offset(str(srt1), str(srt2)) is None

        # Should succeed with relaxed tolerance
        offset = detect_offset(str(srt1), str(srt2), tolerance_ms=1000)
        assert offset == 2000


# ---------------------------------------------------------------------------
# apply_offset tests
# ---------------------------------------------------------------------------


class TestApplyOffset:
    def test_positive_offset(self, tmp_path):
        """Apply positive offset -- all timecodes shift forward."""
        srt_in = tmp_path / "input.srt"
        srt_out = tmp_path / "output.srt"

        _write_srt(
            srt_in,
            [
                (1000, 5000, "First."),
                (6000, 10000, "Second."),
            ],
        )

        apply_offset(str(srt_in), 3000, str(srt_out))

        blocks = parse_srt(str(srt_out))
        assert len(blocks) == 2
        assert blocks[0]["start_ms"] == 4000
        assert blocks[0]["end_ms"] == 8000
        assert blocks[1]["start_ms"] == 9000
        assert blocks[1]["end_ms"] == 13000

    def test_negative_offset(self, tmp_path):
        """Apply negative offset -- timecodes shift backward."""
        srt_in = tmp_path / "input.srt"
        srt_out = tmp_path / "output.srt"

        _write_srt(
            srt_in,
            [
                (5000, 8000, "First."),
                (10000, 14000, "Second."),
            ],
        )

        apply_offset(str(srt_in), -2000, str(srt_out))

        blocks = parse_srt(str(srt_out))
        assert len(blocks) == 2
        assert blocks[0]["start_ms"] == 3000
        assert blocks[0]["end_ms"] == 6000
        assert blocks[1]["start_ms"] == 8000
        assert blocks[1]["end_ms"] == 12000

    def test_zero_offset(self, tmp_path):
        """Zero offset -- timecodes unchanged."""
        srt_in = tmp_path / "input.srt"
        srt_out = tmp_path / "output.srt"

        _write_srt(
            srt_in,
            [
                (1000, 3000, "Hello."),
                (4000, 6000, "World."),
            ],
        )

        apply_offset(str(srt_in), 0, str(srt_out))

        blocks = parse_srt(str(srt_out))
        assert blocks[0]["start_ms"] == 1000
        assert blocks[0]["end_ms"] == 3000
        assert blocks[1]["start_ms"] == 4000
        assert blocks[1]["end_ms"] == 6000

    def test_preserves_text(self, tmp_path):
        """Apply offset preserves block text exactly."""
        srt_in = tmp_path / "input.srt"
        srt_out = tmp_path / "output.srt"

        _write_srt(
            srt_in,
            [
                (1000, 3000, "Sahaja Yoga meditation."),
                (5000, 8000, "Feel the vibrations."),
            ],
        )

        apply_offset(str(srt_in), 1000, str(srt_out))

        blocks = parse_srt(str(srt_out))
        assert blocks[0]["text"] == "Sahaja Yoga meditation."
        assert blocks[1]["text"] == "Feel the vibrations."

    def test_preserves_block_count(self, tmp_path):
        """Block count is preserved after applying offset."""
        srt_in = tmp_path / "input.srt"
        srt_out = tmp_path / "output.srt"

        original_blocks = [(i * 3000, i * 3000 + 2000, f"Block {i}.") for i in range(20)]
        _write_srt(srt_in, original_blocks)

        apply_offset(str(srt_in), 5000, str(srt_out))

        blocks = parse_srt(str(srt_out))
        assert len(blocks) == 20

    def test_sequential_numbering(self, tmp_path):
        """Output SRT has sequential block numbering starting from 1."""
        srt_in = tmp_path / "input.srt"
        srt_out = tmp_path / "output.srt"

        _write_srt(
            srt_in,
            [
                (1000, 3000, "First."),
                (4000, 6000, "Second."),
                (7000, 9000, "Third."),
            ],
        )

        apply_offset(str(srt_in), 500, str(srt_out))

        blocks = parse_srt(str(srt_out))
        for i, b in enumerate(blocks):
            assert b["idx"] == i + 1

    def test_large_offset(self, tmp_path):
        """Large offset (1 hour) applied correctly."""
        srt_in = tmp_path / "input.srt"
        srt_out = tmp_path / "output.srt"

        _write_srt(srt_in, [(1000, 3000, "Start.")])

        offset_1h = 3600000  # 1 hour in ms
        apply_offset(str(srt_in), offset_1h, str(srt_out))

        blocks = parse_srt(str(srt_out))
        assert blocks[0]["start_ms"] == 3601000
        assert blocks[0]["end_ms"] == 3603000

    def test_single_block(self, tmp_path):
        """Single block SRT works correctly."""
        srt_in = tmp_path / "input.srt"
        srt_out = tmp_path / "output.srt"

        _write_srt(srt_in, [(2000, 5000, "Only block.")])

        apply_offset(str(srt_in), 1000, str(srt_out))

        blocks = parse_srt(str(srt_out))
        assert len(blocks) == 1
        assert blocks[0]["start_ms"] == 3000
        assert blocks[0]["end_ms"] == 6000
        assert blocks[0]["text"] == "Only block."

    def test_empty_srt(self, tmp_path):
        """Empty SRT file produces empty output."""
        srt_in = tmp_path / "input.srt"
        srt_out = tmp_path / "output.srt"

        srt_in.write_text("", encoding="utf-8")

        apply_offset(str(srt_in), 1000, str(srt_out))

        blocks = parse_srt(str(srt_out))
        assert len(blocks) == 0

    def test_negative_offset_drops_blocks_before_zero(self, tmp_path):
        """A large negative offset that would push a block's end before
        t=0 must drop that block, and any block whose start goes negative
        gets clamped to 0 so write_srt never emits an invalid timecode."""
        srt_in = tmp_path / "input.srt"
        srt_out = tmp_path / "output.srt"

        _write_srt(
            srt_in,
            [
                (1000, 3000, "Dropped entirely."),
                (4000, 9000, "Clamped start."),
                (20000, 24000, "Kept intact."),
            ],
        )

        apply_offset(str(srt_in), -5000, str(srt_out))

        kept = parse_srt(str(srt_out))
        assert len(kept) == 2
        # First survivor had start=4000 → -1000, clamped to 0; end stays 4000
        assert kept[0]["start_ms"] == 0
        assert kept[0]["end_ms"] == 4000
        # Second survivor shifted normally
        assert kept[1]["start_ms"] == 15000
        assert kept[1]["end_ms"] == 19000

    def test_output_file_is_valid_srt(self, tmp_path):
        """Output file is a valid SRT that can be re-parsed."""
        srt_in = tmp_path / "input.srt"
        srt_out = tmp_path / "output.srt"
        srt_roundtrip = tmp_path / "roundtrip.srt"

        _write_srt(
            srt_in,
            [
                (1000, 4000, "Block A."),
                (5000, 9000, "Block B."),
                (10000, 14000, "Block C."),
            ],
        )

        apply_offset(str(srt_in), 2500, str(srt_out))

        # Re-apply zero offset to roundtrip
        apply_offset(str(srt_out), 0, str(srt_roundtrip))

        blocks_out = parse_srt(str(srt_out))
        blocks_rt = parse_srt(str(srt_roundtrip))

        assert len(blocks_out) == len(blocks_rt)
        for b1, b2 in zip(blocks_out, blocks_rt, strict=True):
            assert b1["start_ms"] == b2["start_ms"]
            assert b1["end_ms"] == b2["end_ms"]
            assert b1["text"] == b2["text"]


# ---------------------------------------------------------------------------
# End-to-end: detect then apply
# ---------------------------------------------------------------------------


class TestDetectThenApply:
    def test_roundtrip(self, tmp_path):
        """Detect offset from two SRTs, apply it to a third, verify timecodes match."""
        srt_ref = tmp_path / "ref.srt"
        srt_shifted = tmp_path / "shifted.srt"
        srt_uk = tmp_path / "uk.srt"
        srt_uk_out = tmp_path / "uk_shifted.srt"

        offset_ms = 3500

        # English reference and shifted version
        en_blocks = [
            (2000, 5000, "Hello everyone."),
            (6000, 9000, "Welcome to Sahaja Yoga."),
            (10000, 14000, "Please sit comfortably."),
        ]
        _write_srt(srt_ref, en_blocks)
        _write_srt(srt_shifted, [(s + offset_ms, e + offset_ms, t) for s, e, t in en_blocks])

        # Ukrainian SRT at reference timing
        uk_blocks = [
            (2000, 5000, "Привіт усім."),
            (6000, 9000, "Ласкаво просимо до Сахаджа Йоги."),
            (10000, 14000, "Будь ласка, сідайте зручно."),
        ]
        _write_srt(srt_uk, uk_blocks)

        # Detect offset
        detected = detect_offset(str(srt_ref), str(srt_shifted))
        assert detected == offset_ms

        # Apply to Ukrainian SRT
        apply_offset(str(srt_uk), detected, str(srt_uk_out))

        blocks = parse_srt(str(srt_uk_out))
        assert len(blocks) == 3
        assert blocks[0]["start_ms"] == 5500
        assert blocks[0]["end_ms"] == 8500
        assert blocks[0]["text"] == "Привіт усім."
        assert blocks[1]["start_ms"] == 9500
        assert blocks[1]["end_ms"] == 12500
        assert blocks[2]["start_ms"] == 13500
        assert blocks[2]["end_ms"] == 17500
