"""Structural guard: the pipeline refreshes the typo-hint wordlist it invalidates.

``site/dict/words_uk.txt`` is generated from the corpus — every
``talks/*/transcript_uk.txt`` and ``talks/*/*/final/uk.srt`` — and committed.
The pipeline's commit job writes exactly those files, so every build lands
vocabulary the committed list does not carry yet.

Nothing catches that at the time: ``ci.yml`` filters ``talks/`` down to
``meta.yaml`` and ``source/whisper.json``, so CI does not run on a pipeline
commit at all. The ``Typo-hint wordlist is current`` guard therefore fires for
the first time on the NEXT, unrelated pull request and fails it — that is how
#1060 (a Dependabot ruff bump) went red, and #1069 had to refresh the list by
hand.

The producer must leave the list consistent: rebuild it after the artifacts are
placed and commit it alongside them.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

REFRESH_STEP = "Refresh typo-hint wordlist"
PLACE_STEP = "Place artifacts into talk directories"
COMMIT_STEP = "Commit via PR"


def _commit_job_steps() -> list[dict]:
    wf = yaml.safe_load((WORKFLOWS / "subtitle-pipeline.yml").read_text(encoding="utf-8"))
    return wf["jobs"]["commit"]["steps"]


def _step_index(steps: list[dict], name: str) -> int:
    for i, step in enumerate(steps):
        if step.get("name") == name:
            return i
    raise AssertionError(f"step {name!r} not found in the commit job")


def test_wordlist_is_rebuilt_between_placing_artifacts_and_committing() -> None:
    steps = _commit_job_steps()
    place = _step_index(steps, PLACE_STEP)
    refresh = _step_index(steps, REFRESH_STEP)
    commit = _step_index(steps, COMMIT_STEP)

    assert place < refresh, "the wordlist must be rebuilt AFTER the new talk files land"
    assert refresh < commit, "the wordlist must be rebuilt BEFORE the bot commit stages it"
    assert "tools.build_wordlist" in steps[refresh]["run"], (
        "the refresh step must run the generator, not re-implement it"
    )
    assert "--check" not in steps[refresh]["run"], "the pipeline must WRITE the list, not merely assert it is current"


def test_refresh_failure_is_not_swallowed() -> None:
    """A stale list must not be able to pass as a clean run.

    `continue-on-error` here would restore exactly the bug this step exists to
    close, except quietly: the job stays green, the commit lands, and the list
    is behind again with nothing on the run to say so.
    """
    steps = _commit_job_steps()
    refresh = steps[_step_index(steps, REFRESH_STEP)]
    assert not refresh.get("continue-on-error"), "the refresh must fail the job, not degrade silently to a stale list"


def test_commit_job_installs_the_generator_dependencies() -> None:
    steps = _commit_job_steps()
    refresh = _step_index(steps, REFRESH_STEP)

    setup = [i for i, s in enumerate(steps) if str(s.get("uses", "")).startswith("actions/setup-python@")]
    assert setup, "the commit job must set up Python to run the generator"
    assert min(setup) < refresh, "Python must be set up before the refresh step"

    installs = [i for i, s in enumerate(steps) if "pip install" in str(s.get("run", ""))]
    assert installs, "the commit job must install the generator's dependencies"
    assert min(installs) < refresh, "dependencies must be installed before the refresh step"


def test_refreshed_wordlist_is_staged_by_the_bot_commit() -> None:
    steps = _commit_job_steps()
    commit_run = steps[_step_index(steps, COMMIT_STEP)]["run"]

    assert "site/dict/words_uk.txt" in commit_run, (
        "a rebuilt list that is never staged leaves main exactly as stale as before"
    )


def test_wordlist_generator_deps_are_runtime_requirements() -> None:
    """The commit job installs requirements.txt only.

    ``tools.build_wordlist`` spell-checks against the vendored hunspell
    dictionary through spylls; with spylls confined to requirements-dev.txt the
    refresh step would die on an ImportError inside a job whose only other work
    is pushing, i.e. after the expensive half of the pipeline has run.
    """
    runtime = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "spylls" in runtime, "spylls is imported by tools.build_wordlist at runtime"
