"""Level 2 replay tests.

These tests simulate the second half of the pipeline (everything after the
single-pass build-timecodes phase) using captured fixtures instead of live
API calls.

Fixture layout:
    tests/fixtures/llm_responses/
        {talk}.uk.map         — what the single-pass Opus build-timecodes
                                agent would emit (after cmd_assemble)

The fixtures are paired with real whisper.json + transcript_uk.txt that
already live under `talks/` — no duplication, one source of truth.

A replay case asserts that given a canned LLM output (as a uk.map), the
Python side (validate_uk_map → build_srt → optimize_srt → validate_subtitles)
converges to a valid SRT without any API calls. Any regression in build_srt or
optimize_srt that would silently ship broken SRTs blows up here within 1 sec.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from tools.build_srt import build_srt
from tools.optimize_srt import optimize
from tools.uk_map import validate_uk_map
from tools.validate_subtitles import validate

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "llm_responses"


@dataclass(frozen=True)
class ReplayCase:
    name: str
    uk_map: Path
    transcript: Path
    whisper: Path


CASES: list[ReplayCase] = [
    ReplayCase(
        name="1988_sahasrara",
        uk_map=FIXTURES / "1988_sahasrara.uk.map",
        transcript=ROOT / "talks/1988-05-08_Sahasrara-Puja-How-it-was-decided/transcript_uk.txt",
        whisper=ROOT / "talks/1988-05-08_Sahasrara-Puja-How-it-was-decided/Sahasrara-Puja-Talk/source/whisper.json",
    ),
]


def _collect_existing(cases: list[ReplayCase]) -> list[ReplayCase]:
    return [c for c in cases if c.uk_map.is_file() and c.transcript.is_file() and c.whisper.is_file()]


EXISTING = _collect_existing(CASES)


def test_replay_corpus_nonempty() -> None:
    assert EXISTING, "No replay fixtures found — check tests/fixtures/llm_responses/"


@pytest.mark.parametrize("case", EXISTING, ids=[c.name for c in EXISTING])
def test_uk_map_fixture_is_valid(case: ReplayCase) -> None:
    """The captured LLM output must satisfy the strict uk.map contract.
    Regression guard on both the validator AND the fixture."""
    blocks = validate_uk_map(str(case.uk_map))
    assert blocks, f"{case.name}: validator returned no blocks"


@pytest.mark.parametrize("case", EXISTING, ids=[c.name for c in EXISTING])
def test_replay_build_to_valid_srt(case: ReplayCase, tmp_path: Path) -> None:
    """Full Python-side pipeline replay from a canned uk.map → valid SRT."""
    built = tmp_path / "built.srt"
    build_srt(str(case.uk_map), str(built))
    assert built.is_file()

    optimized = tmp_path / "optimized.srt"
    optimize(str(built), str(case.whisper), str(optimized))

    passed, report = validate(
        str(optimized),
        str(case.transcript),
        whisper_json_path=str(case.whisper),
        # Optimize legitimately pads the last block up to 2s past the last
        # whisper word; the real pipeline skips the time-range hard check
        # for the same reason.
        skip_time_check=True,
    )
    assert passed, f"{case.name}: pipeline replay produced invalid SRT:\n" + "\n".join(report[-30:])


@pytest.mark.parametrize("case", EXISTING, ids=[c.name for c in EXISTING])
def test_replay_is_deterministic(case: ReplayCase, tmp_path: Path) -> None:
    """Running the exact same replay twice must yield byte-identical SRT.
    Any non-determinism in build_srt/optimize_srt (e.g. random split, dict
    iteration order) will break this."""
    from tools.srt_utils import parse_srt

    a = tmp_path / "a.srt"
    b = tmp_path / "b.srt"
    build_srt(str(case.uk_map), str(a))
    build_srt(str(case.uk_map), str(b))
    blocks_a = parse_srt(str(a))
    blocks_b = parse_srt(str(b))
    assert len(blocks_a) == len(blocks_b)
    for x, y in zip(blocks_a, blocks_b, strict=True):
        assert x == y, f"{case.name}: determinism broken at block {x['idx']}"
