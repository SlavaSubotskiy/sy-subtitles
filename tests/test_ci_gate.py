"""Guards for the single required check on `main`.

A required status check has to be a check that is ALWAYS reported, whatever
the pull request touched. The lanes in ci.yml are not: they were gated by a
workflow-level `paths` filter, so a pull request outside those paths produced
no run at all — requiring any of them by name would leave such a PR waiting
forever on a check that is never going to arrive.

Worse, without a required check nothing notices when a run simply fails to
appear. That is how #1069 merged: its CI run was never dispatched (a
transient Actions failure — two probes later confirmed the path filter itself
was fine), no lane reported, and the PR was mergeable anyway.

So ci.yml now runs on every pull request and decides INSIDE the workflow which
lanes are needed, and `gate` — which depends on all of them and always runs —
is the one check to require.
"""

import re
import subprocess
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"

GATE = "gate"


def _load() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _triggers() -> dict:
    # PyYAML parses the bare `on:` key as boolean True.
    return _load()[True]


def _gate() -> dict:
    return _load()["jobs"][GATE]


def test_ci_runs_on_every_pull_request() -> None:
    """A path-filtered workflow cannot supply an always-present check."""
    pr = _triggers()["pull_request"] or {}
    assert "paths" not in pr and "paths-ignore" not in pr, (
        "a filtered trigger means no run — and therefore no gate — on PRs outside it"
    )


def test_ci_runs_when_a_draft_is_marked_ready() -> None:
    """`ready_for_review` is not in the default activity types.

    Every open PR in this repository is a draft (the SPA's edit auto-sync works
    there), and flipping one to ready pushes no commit. With only the default
    types — opened, synchronize, reopened — that transition produces no run, so
    `gate` never reports and the PR is unmergeable with nothing left to nudge
    it. Requiring a check makes this the difference between "not ready yet" and
    "permanently stuck". sync-subtitles.yml opts in for the same reason.
    """
    pr = _triggers()["pull_request"] or {}
    assert "ready_for_review" in (pr.get("types") or []), (
        "a draft marked ready must produce a run, or its required check never arrives"
    )


def test_the_path_list_lives_in_exactly_one_place() -> None:
    """Two copies of the list drift, and the drift is invisible until it bites."""
    push = _triggers()["push"] or {}
    assert "paths" not in push, "the change detector owns the path list; a second copy on the trigger drifts from it"


def test_gate_depends_on_every_other_job() -> None:
    """A lane the gate does not watch is a lane that can fail unnoticed."""
    jobs = _load()["jobs"]
    watched = set(_gate()["needs"])
    assert watched == set(jobs) - {GATE}, f"gate must depend on every other job; missing {set(jobs) - {GATE} - watched}"


def test_gate_reports_even_when_a_lane_fails() -> None:
    """`always()` is what makes it a check rather than a casualty."""
    assert "always()" in str(_gate().get("if", "")), (
        "without always() the gate is skipped by a failing lane and never reports"
    )


def _gate_script() -> str:
    steps = _gate()["steps"]
    script = next(s["run"] for s in steps if "run" in s)
    # The step reads only $RESULTS, so it runs standalone.
    assert "RESULTS" in script
    return script


def _run_gate(results: str) -> int:
    return subprocess.run(
        ["bash", "-c", _gate_script()],
        env={"RESULTS": results, "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    ).returncode


def test_gate_passes_when_every_lane_succeeded() -> None:
    assert _run_gate("success success success success") == 0


def test_gate_passes_when_a_lane_was_not_needed() -> None:
    """Skipped is the detector saying the lane had nothing to check."""
    assert _run_gate("success skipped skipped skipped") == 0


def test_gate_fails_on_a_failed_lane() -> None:
    assert _run_gate("success failure success success") != 0


def test_gate_fails_on_a_cancelled_lane() -> None:
    """A cancelled lane proved nothing; passing it off as green is the bug."""
    assert _run_gate("success cancelled success success") != 0


def test_gate_fails_on_no_results_at_all() -> None:
    """An empty expansion must not read as unanimous success."""
    assert _run_gate("") != 0


def test_pull_request_runs_supersede_rather_than_stack() -> None:
    """The SPA's edit auto-sync pushes to a draft PR every few seconds.

    Now that the workflow is unfiltered those pushes reach it, so each new one
    must cancel the run before it. `main` is deliberately left alone: cancelling
    there would drop the record for a commit that is already merged.
    """
    concurrency = _load()["concurrency"]
    assert "pull_request" in str(concurrency["cancel-in-progress"]), (
        "cancel PR runs only — a main run cancelled by the next merge leaves no record"
    )
    assert re.search(r"pull_request\.number", str(concurrency["group"])), (
        "the group must be per-PR, or one PR's push cancels another's run"
    )
