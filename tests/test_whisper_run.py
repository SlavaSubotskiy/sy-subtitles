"""Tests for whisper_run hallucination filter and segment processing."""

import pytest

from tools.whisper_run import is_hallucination


class TestIsHallucination:
    """Test hallucination detection for whisper segments."""

    def test_empty_string(self):
        assert is_hallucination("") is True

    def test_whitespace_only(self):
        assert is_hallucination("   ") is True

    def test_single_dot(self):
        assert is_hallucination(".") is True

    def test_multiple_dots(self):
        assert is_hallucination("...") is True

    def test_dots_with_spaces(self):
        assert is_hallucination(". . .") is True

    def test_ellipsis_unicode(self):
        assert is_hallucination("…") is True

    def test_mixed_dots_ellipsis(self):
        assert is_hallucination("...… .") is True

    def test_real_speech(self):
        assert is_hallucination("Today is the nineteenth Sahasrara day.") is False

    def test_short_real_word(self):
        assert is_hallucination("Yes") is False

    def test_sentence_with_dots(self):
        assert is_hallucination("I have to tell you...") is False

    def test_single_word(self):
        assert is_hallucination("Kundalini") is False

    def test_dot_with_text(self):
        assert is_hallucination(". hello") is False

    def test_leading_trailing_spaces(self):
        assert is_hallucination("  .  ") is True

    def test_leading_trailing_real(self):
        assert is_hallucination("  hello  ") is False


class TestWhisperRunConfig:
    """Test that whisper_run uses correct anti-hallucination config."""

    def test_imports_faster_whisper(self):
        """Verify whisper_run uses faster-whisper, not openai-whisper."""
        import inspect

        from tools.whisper_run import run_whisper

        source = inspect.getsource(run_whisper)
        assert "faster_whisper" in source
        assert "WhisperModel" in source

    def test_vad_filter_enabled(self):
        """Verify VAD filter is enabled in transcribe call."""
        import inspect

        from tools.whisper_run import run_whisper

        source = inspect.getsource(run_whisper)
        assert "vad_filter=True" in source

    def test_condition_on_previous_text_false(self):
        """Verify condition_on_previous_text is disabled."""
        import inspect

        from tools.whisper_run import run_whisper

        source = inspect.getsource(run_whisper)
        assert "condition_on_previous_text=False" in source

    def test_hallucination_silence_threshold_set(self):
        """Verify hallucination_silence_threshold is configured."""
        import inspect

        from tools.whisper_run import run_whisper

        source = inspect.getsource(run_whisper)
        assert "hallucination_silence_threshold" in source

    def test_repetition_penalty_set(self):
        """Verify repetition_penalty is > 1."""
        import inspect

        from tools.whisper_run import run_whisper

        source = inspect.getsource(run_whisper)
        assert "repetition_penalty=1.2" in source


class TestHallucinationOnRealData:
    """Test hallucination filter on patterns from real whisper output."""

    @pytest.fixture
    def puja_whisper(self):
        """Load puja whisper.json if available (before cleanup)."""
        # Use the known hallucination patterns from the puja video
        return [
            {"text": ".", "start": 62.26, "end": 62.3},
            {"text": ".", "start": 108.0, "end": 108.8},
            {"text": "", "start": 109.8, "end": 109.8},
            {"text": ".", "start": 116.0, "end": 116.3},
            {"text": "  .  ", "start": 120.0, "end": 120.5},
            {"text": "...", "start": 130.0, "end": 131.0},
            {"text": "… .", "start": 140.0, "end": 141.0},
        ]

    def test_all_puja_segments_detected_as_hallucination(self, puja_whisper):
        for seg in puja_whisper:
            assert is_hallucination(seg["text"]) is True, f"Should detect hallucination: {seg['text']!r}"

    def test_real_talk_segments_pass(self):
        real_segments = [
            "Today is the 19th Sahastrara day.",
            "If you count the first one, the day Sahastrara was opened.",
            "They had a big meeting in the heavens.",
            "I am sure it will work out. Next year I hope I will have some good news.",
        ]
        for text in real_segments:
            assert is_hallucination(text) is False, f"Should pass real speech: {text!r}"
