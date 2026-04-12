"""Level 3 property-based invariants.

Hypothesis-generated SRT/segmentation corpora run through tools/* to prove
invariants that must hold for ANY input, not just the handful we hand-wrote.

Scope kept tight deliberately: property tests are cheap when invariants are
obvious, catastrophic when they're not. Every property here has a single
line of rationale and fails loud with a minimal example.
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tools.config import OptimizeConfig
from tools.offset_srt import apply_offset
from tools.srt_utils import parse_srt, write_srt
from tools.text_segmentation import MAX_CPL, build_blocks_from_paragraphs
from tools.uk_map import UkMapBlock, UkMapError, parse_uk_map, validate_uk_map
from tools.validate_subtitles import validate

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Readable Ukrainian-ish words: letters only so split-on-punctuation logic
# doesn't drown the invariant in punctuation edge cases that are already
# covered by unit tests.
_words = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
    min_size=1,
    max_size=8,
)
_sentences = st.lists(_words, min_size=1, max_size=12).map(lambda ws: " ".join(ws) + ".")
_paragraphs = st.lists(_sentences, min_size=1, max_size=5).map(" ".join)
paragraphs_strategy = st.lists(_paragraphs, min_size=1, max_size=10)


@st.composite
def uk_map_blocks(draw) -> list[UkMapBlock]:
    """Generate a sequence of strictly-ordered uk.map blocks that also satisfy
    CPS/duration/CPL invariants — so they are valid end-to-end, not just to
    the parser."""
    config = OptimizeConfig()
    count = draw(st.integers(min_value=1, max_value=30))
    out: list[UkMapBlock] = []
    cursor = draw(st.integers(min_value=0, max_value=5000))
    for i in range(count):
        raw_text = draw(_sentences)
        # Parser strips leading/trailing whitespace so roundtrip must match.
        text = (raw_text[: MAX_CPL - 1] or ".").strip() or "."
        # Guarantee CPS ≤ hard_max_cps AND duration ≥ min_duration_ms so the
        # generated block survives strict validation.
        cps_min_ms = int(len(text) * 1000 / config.hard_max_cps) + 50
        min_duration = max(config.min_duration_ms, cps_min_ms)
        duration = draw(st.integers(min_value=min_duration, max_value=min_duration + 5000))
        gap = draw(st.integers(min_value=config.min_gap_ms, max_value=500))
        start = cursor
        end = start + duration
        out.append(UkMapBlock(idx=i + 1, start_ms=start, end_ms=end, text=text))
        cursor = end + gap
    return out


def _write_uk_map(blocks: list[UkMapBlock], path: Path) -> None:
    from tools.srt_utils import ms_to_time

    lines = [f"{b.idx} | {ms_to_time(b.start_ms)} | {ms_to_time(b.end_ms)} | {b.text}" for b in blocks]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_srt(blocks: list[UkMapBlock], path: Path) -> None:
    write_srt([b.as_dict() for b in blocks], str(path))


# ---------------------------------------------------------------------------
# Invariant 1: canonical segmentation respects CPL for all paragraph inputs
# ---------------------------------------------------------------------------


@given(paragraphs_strategy)
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_build_blocks_never_exceeds_cpl(paragraphs: list[str]) -> None:
    blocks = build_blocks_from_paragraphs(paragraphs)
    for b in blocks:
        assert len(b["text"]) <= MAX_CPL or len(b["text"].split()) == 1, f"block over CPL: {b['text']!r}"


@given(paragraphs_strategy)
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_build_blocks_ids_sequential(paragraphs: list[str]) -> None:
    blocks = build_blocks_from_paragraphs(paragraphs)
    for i, b in enumerate(blocks, 1):
        assert b["id"] == i


# ---------------------------------------------------------------------------
# Invariant 2: uk.map parser round-trips through serialize → validate
# ---------------------------------------------------------------------------


@given(uk_map_blocks())
@settings(max_examples=100, deadline=None)
def test_uk_map_roundtrip(tmp_path_factory, blocks: list[UkMapBlock]) -> None:
    path = tmp_path_factory.mktemp("uk_map") / "fixture.uk.map"
    _write_uk_map(blocks, path)
    parsed = validate_uk_map(str(path))
    assert len(parsed) == len(blocks)
    for a, b in zip(parsed, blocks, strict=True):
        assert a.idx == b.idx
        assert a.start_ms == b.start_ms
        assert a.end_ms == b.end_ms
        assert a.text == b.text


# ---------------------------------------------------------------------------
# Invariant 3: validate_uk_map rejects any line with end <= start
# ---------------------------------------------------------------------------


@given(
    st.integers(min_value=0, max_value=100000),
    st.integers(min_value=0, max_value=100000),
    _sentences,
)
@settings(max_examples=100, deadline=None)
def test_uk_map_rejects_non_positive_duration(tmp_path_factory, a: int, b: int, text: str) -> None:
    if a == b:
        return
    start, end = (a, b) if a < b else (b, a)
    # Deliberately swap so end <= start.
    path = tmp_path_factory.mktemp("uk_map_bad") / "bad.uk.map"
    from tools.srt_utils import ms_to_time

    path.write_text(
        f"1 | {ms_to_time(end)} | {ms_to_time(start)} | {text}\n",
        encoding="utf-8",
    )
    try:
        parse_uk_map(str(path), strict=True)
    except UkMapError as e:
        assert "start" in str(e) and "end" in str(e)
    else:
        raise AssertionError("expected UkMapError")


# ---------------------------------------------------------------------------
# Invariant 4: offset_srt.apply_offset(0) is identity
# ---------------------------------------------------------------------------


@given(uk_map_blocks())
@settings(max_examples=50, deadline=None)
def test_offset_zero_is_identity(tmp_path_factory, blocks: list[UkMapBlock]) -> None:
    src = tmp_path_factory.mktemp("offset_src") / "in.srt"
    dst = tmp_path_factory.mktemp("offset_dst") / "out.srt"
    _write_srt(blocks, src)
    apply_offset(str(src), 0, str(dst))
    a = parse_srt(str(src))
    b = parse_srt(str(dst))
    assert a == b


# ---------------------------------------------------------------------------
# Invariant 5: any structurally-valid uk.map parses → writes to SRT that
# passes validate_subtitles on the trivial CPL/duration/gap axes.
# (Text-preservation is excluded because transcripts are not generated.)
# ---------------------------------------------------------------------------


@given(uk_map_blocks())
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_uk_map_to_srt_satisfies_structural_validation(tmp_path_factory, blocks: list[UkMapBlock]) -> None:
    srt_path = tmp_path_factory.mktemp("srt") / "out.srt"
    _write_srt(blocks, srt_path)
    # Minimal transcript: one paragraph with all block texts concatenated —
    # guarantees text_check passes even though the generator is naive.
    transcript_path = tmp_path_factory.mktemp("tr") / "transcript.txt"
    transcript_path.write_text("\n\n".join(b.text for b in blocks) + "\n", encoding="utf-8")
    passed, _ = validate(
        str(srt_path),
        str(transcript_path),
        whisper_json_path=None,
        skip_time_check=True,
    )
    assert passed, "structurally-valid generated blocks failed validation"


# ---------------------------------------------------------------------------
# Invariant 6: OptimizeConfig defaults stay mutually consistent
# ---------------------------------------------------------------------------


def test_config_invariants() -> None:
    c = OptimizeConfig()
    assert c.min_duration_ms < c.max_duration_ms
    assert c.target_cps < c.hard_max_cps
    assert c.min_gap_ms >= 0
    assert c.max_cpl > 0
