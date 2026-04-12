"""CLI smoke test for tools.pipeline_dryrun.

Spawns the CLI as a subprocess (so argparse + module wiring is exercised)
and asserts it returns 0 on the 1988 Sahasrara fixture. This catches
breakage in the dryrun driver itself, which is the thing rev'yuers will
reach for when debugging pipeline issues locally.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TALK_DIR = ROOT / "talks/1988-05-08_Sahasrara-Puja-How-it-was-decided"
FIXTURE = ROOT / "tests/fixtures/llm_responses/1988_sahasrara.uk.map"


@pytest.mark.skipif(
    not (TALK_DIR.is_dir() and FIXTURE.is_file()),
    reason="1988 talk or fixture missing",
)
def test_dryrun_cli_passes_on_canonical_fixture(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.pipeline_dryrun",
            "--talk-dir",
            str(TALK_DIR),
            "--video-slug",
            "Sahasrara-Puja-Talk",
            "--uk-map",
            str(FIXTURE),
            "--work-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, (
        f"dryrun failed (stdout tail):\n{result.stdout[-2000:]}\nSTDERR:\n{result.stderr[-500:]}"
    )
    assert "DRYRUN PASSED" in result.stdout
    # Work artifacts stay on disk for inspection.
    assert (tmp_path / "built.srt").is_file()
    assert (tmp_path / "optimized.srt").is_file()


def test_dryrun_cli_fails_on_bad_fixture(tmp_path: Path) -> None:
    """Dryrun must refuse a broken uk.map loudly (non-zero exit + clear error)."""
    bad_fixture = tmp_path / "bad.uk.map"
    bad_fixture.write_text("1 | 00:00:aa,000 | 00:00:02,000 | Текст\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.pipeline_dryrun",
            "--talk-dir",
            str(TALK_DIR),
            "--video-slug",
            "Sahasrara-Puja-Talk",
            "--uk-map",
            str(bad_fixture),
            "--work-dir",
            str(tmp_path / "work"),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 1
    assert "DRYRUN FAILED" in result.stdout
    assert "uk.map" in result.stdout
