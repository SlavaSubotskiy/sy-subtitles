"""Golden-file regression tests on real talks.

These tests treat the merged-to-main `final/uk.srt` files as the oracle and
enforce two cross-tool invariants that the pipeline should never break:

1. `validate_subtitles` passes on every shipped uk.srt against its
   `transcript_uk.txt` (text preservation, numbering, durations, gaps, CPS, CPL).
2. Running `optimize_srt` on a shipped uk.srt produces an output that still
   passes `validate_subtitles` and is block-stable (idempotency contract —
   the second run changes nothing material beyond report lines).

Any new change to build_map, build_srt, optimize_srt, sync_* or the validator
config will trip these the moment it regresses shipped data. This is the
"real talk" regression surface the audit asked for.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from tools.optimize_srt import optimize
from tools.srt_utils import parse_srt
from tools.validate_subtitles import validate


def _mode_flags(srt_path: Path) -> dict:
    """Return validate() kwargs matching how the pipeline validated this video.

    Reads `final/build_manifest.yaml` written during pipeline commit. The
    manifest tells us which mode produced the SRT so golden validation
    mirrors the pipeline's `--skip-*` flags exactly — running stricter
    than production would flag legitimate pipeline outputs as broken.

    Legacy talks built before the manifest landed keep their historical
    strict treatment (all checks on).
    """
    manifest_path = srt_path.parent / "build_manifest.yaml"
    if not manifest_path.is_file():
        return {}  # legacy: strict validate
    with open(manifest_path, encoding="utf-8") as f:
        manifest = yaml.safe_load(f) or {}
    role = manifest.get("role")
    mode = manifest.get("mode")
    if role == "secondary":
        # Secondary = derivative (offset / resync from primary). Text came
        # from primary (already validated); timing is shifted/warped, CPS
        # may spike in a few places where primary's silences collapse.
        return {"skip_text_check": True, "skip_time_check": True, "skip_cps_check": True}
    if role == "primary" and mode == "en-srt":
        # En-srt primary: transcript-only content is legitimately dropped
        # by Opus (no EN counterpart), so text preservation is replaced by
        # a block-count sanity against the EN SRT.
        en_srt = srt_path.parent.parent / "source" / "en.srt"
        flags = {"skip_text_check": True}
        if en_srt.is_file():
            flags["en_srt_path"] = str(en_srt)
            flags["compare_block_count"] = True
        return flags
    # Primary + whisper mode: strict default.
    return {}


ROOT = Path(__file__).resolve().parent.parent
TALKS = ROOT / "talks"


def _discover_talks() -> list[tuple[str, Path, Path]]:
    """Yield (id, srt, transcript) for every video that has a final/uk.srt
    *and* a sibling transcript_uk.txt at talk level."""
    results: list[tuple[str, Path, Path]] = []
    if not TALKS.is_dir():
        return results
    for talk_dir in sorted(TALKS.iterdir()):
        if not talk_dir.is_dir():
            continue
        transcript = talk_dir / "transcript_uk.txt"
        if not transcript.is_file():
            continue
        for video_dir in sorted(talk_dir.iterdir()):
            if not video_dir.is_dir():
                continue
            srt = video_dir / "final" / "uk.srt"
            if srt.is_file():
                results.append((f"{talk_dir.name}/{video_dir.name}", srt, transcript))
    return results


TALK_CASES = _discover_talks()
# Minimum coverage guard — regression test is meaningless if it runs on nothing.
MIN_TALKS = int(os.environ.get("GOLDEN_MIN_TALKS", "3"))

# Known-broken shipped talks. xfail(strict=True) means:
#   - still broken → expected failure (test stays green)
#   - now passing  → strict xfail fails the suite, forcing us to remove the mark
# Add a reason when adding an entry. Remove the entry the moment the talk is fixed.
KNOWN_BROKEN_VALIDATION: dict[str, str] = {
    "1979-02-25_Puja-In-Pune-Marathi/Mahashivaratri-Puja": "text preservation drift",
    "1979-12-10_Christmas-And-Its-Relationship-To-Lord-Jesus-1979-2/The-Incarnation-Of-Christ": "text preservation drift",
    "1980-03-23_Birthday-Puja/Birthday-Puja": "duration > 21s",
    "1981-03-21_Birthday-Puja-1981-Sydney/Birthday-Puja": "text preservation drift",
    "1981-03-21_Birthday-Puja-1981-Sydney/Birthday-Puja-Talk": "text preservation drift",
    "1982-07-11_From-Heart-To-Sahastrar-Derby/From-Heart-to-Sahasrara": "text preservation drift",
    "1983-03-30_Celebration-Of-Birthday-In-Bombay/Birthday-Puja-English-Talk": "text preservation drift",
    "1984-03-22_Birthday-Puja/Birthday-Puja-Be-Sweet": "duration > 21s",
    "1984-03-22_Birthday-Puja/Birthday-Puja-Talk-Be-Sweet": "legacy SRT contains stripped stage directions; rebuild via pipeline",
    "1992-02-25_Talk-To-Yogis-In-Christchurch/Talk-to-Sahaja-Yogis-Religion-is-Within": "title subtitle at 0-28.8s exceeds 21s max; pipeline uses --skip-duration-check, golden does not",
    "2001-04-22_Easter-Puja-You-Cannot-Resurrect-Yourself-Without-Controlling-Agnya/Easter-Puja-Talk-Istanbul-Turkey-DP-RAW": "final transcript blessing dropped by builder; duration < 1200ms on one block",
}

KNOWN_NON_IDEMPOTENT: dict[str, str] = {
    # Talks where optimize_srt is NOT idempotent due to shipped text drift —
    # the first pass tries to fix text that can't round-trip, and the second
    # pass drifts differently. These overlap with KNOWN_BROKEN_VALIDATION
    # entries where the drift is in text preservation, not duration (the
    # duration-only talks now pass because the test uses skip_duration_check).
    "1979-02-25_Puja-In-Pune-Marathi/Mahashivaratri-Puja": "legacy SRT still contains stage-direction-only blocks that validate now strips from the transcript",
    "1979-12-10_Christmas-And-Its-Relationship-To-Lord-Jesus-1979-2/The-Incarnation-Of-Christ": "text preservation drift",
    "1980-03-23_Birthday-Puja/Birthday-Puja": "text preservation drift",
    "1981-03-21_Birthday-Puja-1981-Sydney/Birthday-Puja-Talk": "text preservation drift",
    "1982-07-11_From-Heart-To-Sahastrar-Derby/From-Heart-to-Sahasrara": "text preservation drift",
    "1983-03-30_Celebration-Of-Birthday-In-Bombay/Birthday-Puja-English-Talk": "text preservation drift",
    "1984-03-22_Birthday-Puja/Birthday-Puja-Talk-Be-Sweet": "legacy SRT contains stripped stage directions; rebuild via pipeline",
    "2001-04-22_Easter-Puja-You-Cannot-Resurrect-Yourself-Without-Controlling-Agnya/Easter-Puja-Talk-Istanbul-Turkey-DP-RAW": "final transcript blessing dropped by builder; duration < 1200ms on one block",
}


def _case_params(cases, known_broken):
    params = []
    for talk_id, srt, tr in cases:
        marks = []
        if talk_id in known_broken:
            marks.append(pytest.mark.xfail(reason=known_broken[talk_id], strict=True))
        params.append(pytest.param(talk_id, srt, tr, marks=marks, id=talk_id))
    return params


def test_golden_corpus_is_nonempty() -> None:
    assert len(TALK_CASES) >= MIN_TALKS, (
        f"Golden test corpus has only {len(TALK_CASES)} talks, "
        f"expected ≥ {MIN_TALKS}. Check tests/fixtures discovery or add talks."
    )


@pytest.mark.parametrize(
    ("talk_id", "srt_path", "transcript_path"),
    _case_params(TALK_CASES, KNOWN_BROKEN_VALIDATION) or [pytest.param("<empty>", None, None)],
)
def test_shipped_srt_passes_validation(talk_id: str, srt_path: Path, transcript_path: Path) -> None:
    """Every shipped uk.srt must pass validate_subtitles — under the same
    mode-appropriate flags the pipeline used when producing it.

    Mode is read from `final/build_manifest.yaml`. Legacy talks without a
    manifest still get the strictest default."""
    passed, report = validate(
        str(srt_path),
        str(transcript_path),
        whisper_json_path=None,
        report_path=None,
        **_mode_flags(srt_path),
    )
    assert passed, f"{talk_id} failed validation:\n" + "\n".join(report[-40:])


@pytest.mark.parametrize(
    ("talk_id", "srt_path", "transcript_path"),
    _case_params(TALK_CASES, KNOWN_NON_IDEMPOTENT) or [pytest.param("<empty>", None, None)],
)
def test_optimize_idempotent_on_shipped(
    talk_id: str,
    srt_path: Path,
    transcript_path: Path,
    tmp_path: Path,
) -> None:
    """Running optimize_srt on an already-shipped file must:
    - not lose/add blocks in a way that breaks validation
    - be stable under a second run (block count + timings don't drift)
    This catches regressions where a new optimizer rule keeps rewriting stable SRT.
    """
    first = tmp_path / "first.srt"
    second = tmp_path / "second.srt"

    optimize(str(srt_path), None, str(first))
    # Mirror the real pipeline's validate flags — duration splits are
    # skipped in the shipped flow, so the idempotency test shouldn't be
    # stricter than production. Mode-specific flags come from the shipped
    # build_manifest.yaml (whisper/en-srt/secondary), not `first` (which
    # is in a tmp dir with no manifest sibling).
    mode_flags = _mode_flags(srt_path)
    passed, report = validate(str(first), str(transcript_path), skip_duration_check=True, **mode_flags)
    assert passed, f"{talk_id}: first-pass optimize broke validation:\n" + "\n".join(report[-40:])

    optimize(str(first), None, str(second))
    blocks1 = parse_srt(str(first))
    blocks2 = parse_srt(str(second))
    assert len(blocks1) == len(blocks2), (
        f"{talk_id}: optimize not idempotent — block count drifted {len(blocks1)} → {len(blocks2)}"
    )
    for a, b in zip(blocks1, blocks2, strict=True):
        assert a["text"] == b["text"], f"{talk_id}: text drift in block {a.get('idx')}"
        assert a["start_ms"] == b["start_ms"] and a["end_ms"] == b["end_ms"], (
            f"{talk_id}: timing drift in block {a.get('idx')}: "
            f"{a['start_ms']}-{a['end_ms']} → {b['start_ms']}-{b['end_ms']}"
        )
