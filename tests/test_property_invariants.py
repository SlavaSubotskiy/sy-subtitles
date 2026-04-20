"""Level 3 property-based invariants.

Hypothesis-generated SRT/segmentation corpora run through tools/* to prove
invariants that must hold for ANY input, not just the handful we hand-wrote.

Scope kept tight deliberately: property tests are cheap when invariants are
obvious, catastrophic when they're not. Every property here has a single
line of rationale and fails loud with a minimal example.
"""

from __future__ import annotations

from dataclasses import dataclass

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tools.config import OptimizeConfig
from tools.offset_srt import apply_offset
from tools.srt_utils import parse_srt, write_srt
from tools.text_segmentation import MAX_CPL, build_blocks_from_paragraphs
from tools.validate_subtitles import validate


@dataclass(frozen=True)
class Block:
    """Minimal SRT-block fixture for property tests (was tools.uk_map.Block)."""

    idx: int
    start_ms: int
    end_ms: int
    text: str

    def as_dict(self) -> dict:
        return {"idx": self.idx, "start_ms": self.start_ms, "end_ms": self.end_ms, "text": self.text}


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
def uk_map_blocks(draw) -> list[Block]:
    """Generate a strictly-ordered block sequence satisfying CPS/duration/CPL
    invariants — valid end-to-end for build_srt / validate_subtitles."""
    config = OptimizeConfig()
    count = draw(st.integers(min_value=1, max_value=30))
    out: list[Block] = []
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
        out.append(Block(idx=i + 1, start_ms=start, end_ms=end, text=text))
        cursor = end + gap
    return out


def _write_srt(blocks: list[Block], path) -> None:
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
# Invariant 2: offset_srt.apply_offset(0) is identity
# ---------------------------------------------------------------------------


@given(uk_map_blocks())
@settings(max_examples=50, deadline=None)
def test_offset_zero_is_identity(tmp_path_factory, blocks: list[Block]) -> None:
    src = tmp_path_factory.mktemp("offset_src") / "in.srt"
    dst = tmp_path_factory.mktemp("offset_dst") / "out.srt"
    _write_srt(blocks, src)
    apply_offset(str(src), 0, str(dst))
    a = parse_srt(str(src))
    b = parse_srt(str(dst))
    assert a == b


# ---------------------------------------------------------------------------
# Invariant 3: any structurally-valid block sequence writes an SRT that
# passes validate_subtitles on CPL/duration/gap axes.
# (Text-preservation is excluded because transcripts are not generated.)
# ---------------------------------------------------------------------------


@given(uk_map_blocks())
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_blocks_to_srt_satisfy_structural_validation(tmp_path_factory, blocks: list[Block]) -> None:
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
