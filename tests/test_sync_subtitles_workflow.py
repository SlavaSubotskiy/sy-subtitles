"""Guards for .github/workflows/sync-subtitles.yml.

The SPA's edit auto-sync commits real subtitle/transcript files to a DRAFT
PR on every background push (1.5s after a field blur). Without a draft
guard each of those commits would trigger the full SRT<->transcript
reconciliation run — a CI storm and bot commits racing the client.
The sync must run only for non-draft PRs, and must fire when the draft
is flipped to ready (event type ready_for_review).
"""

from pathlib import Path

import yaml

WORKFLOW = Path(__file__).parent.parent / ".github" / "workflows" / "sync-subtitles.yml"


def _load():
    return yaml.safe_load(WORKFLOW.read_text())


def test_triggers_on_ready_for_review():
    wf = _load()
    # PyYAML parses the bare `on:` key as boolean True.
    pr = wf[True]["pull_request"]
    assert "types" in pr, "pull_request needs explicit types to include ready_for_review"
    assert set(pr["types"]) == {"opened", "synchronize", "reopened", "ready_for_review"}


def test_sync_job_skips_draft_prs():
    wf = _load()
    cond = wf["jobs"]["sync"].get("if", "")
    assert "github.event.pull_request.draft == false" in cond, (
        "the sync job must not run on draft PRs (edit auto-sync pushes there)"
    )


def test_workflow_has_a_concurrency_group_per_pr():
    """Overlapping runs race on the final push.

    The loser is rejected non-fast-forward, which surfaces as a spurious
    red check on a PR whose sync actually succeeded.
    """
    wf = _load()
    group = wf["concurrency"]["group"]
    assert "pull_request.number" in group, "concurrency must be scoped per PR, not global"
    assert wf["concurrency"]["cancel-in-progress"] is True


def test_workflow_does_not_pass_a_base_sha():
    """The baseline comes from git history, not from the PR base.

    Diffing from the PR base replays every edit the bot already committed,
    which is why no sync run has ever been green twice.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "base.sha" not in text
    assert "--base-sha" not in text


def test_bot_commit_carries_the_trailer_the_resolver_looks_for():
    """The baseline is found by trailer; a commit without it is invisible.

    Asserted against the constant itself so the two can never drift.
    """
    from tools.sync_pr import BOT_AUTHOR, SYNC_TRAILER

    text = WORKFLOW.read_text(encoding="utf-8")
    assert SYNC_TRAILER in text, "the bot commit must carry the sync trailer"
    assert f'git config user.name "{BOT_AUTHOR}"' in text


def test_commit_step_only_runs_on_success():
    """A failed sync leaves a clean tree, so there is nothing to preserve.

    `if: always()` used to commit whatever had landed before the failure —
    a red check and a half-applied push at the same time.
    """
    wf = _load()
    steps = wf["jobs"]["sync"]["steps"]
    commit = next(s for s in steps if s.get("name") == "Commit and push")
    assert commit.get("if") == "success()", "a failed sync must never push a partial result"


def _step_index(steps: list[dict], name: str) -> int:
    for i, step in enumerate(steps):
        if step.get("name") == name:
            return i
    raise AssertionError(f"step {name!r} not found in the sync job")


def test_wordlist_is_refreshed_before_the_bot_commit():
    """A reviewer's edit is a corpus change, and the corpus feeds the wordlist.

    site/dict/words_uk.txt is generated from transcript_uk.txt and final/uk.srt
    — the two files this bot rewrites. Rename a deity or fix a transliteration
    and the committed list no longer describes the text the PR carries, so the
    SPA underlines the very spelling the reviewer just chose. The bot must
    leave the PR self-consistent, exactly as the pipeline does for the talks
    it builds (tests/test_pipeline_wordlist_refresh.py).
    """
    steps = _load()["jobs"]["sync"]["steps"]
    sync = _step_index(steps, "Sync, optimize, validate")
    refresh = _step_index(steps, "Refresh typo-hint wordlist")
    commit = _step_index(steps, "Commit and push")

    assert sync < refresh, "the wordlist must be rebuilt AFTER the sync rewrites the text"
    assert refresh < commit, "the wordlist must be rebuilt BEFORE the bot commit stages it"
    assert "tools.build_wordlist" in steps[refresh]["run"]
    assert "--check" not in steps[refresh]["run"], "the bot must WRITE the list, not merely assert it is current"

    # The generator imports spylls; this job installs the runtime set only.
    installs = [i for i, s in enumerate(steps) if "pip install" in str(s.get("run", ""))]
    assert installs and min(installs) < refresh, "dependencies must be installed before the refresh step"


def test_wordlist_refresh_is_gated_on_a_successful_sync():
    """A failed sync commits nothing, so rebuilding from that tree is noise."""
    steps = _load()["jobs"]["sync"]["steps"]
    refresh = steps[_step_index(steps, "Refresh typo-hint wordlist")]
    assert refresh.get("if") == "success()"
    assert not refresh.get("continue-on-error"), "a swallowed refresh restores the stale-list bug quietly"


def test_refreshed_wordlist_is_staged_by_the_bot_commit():
    steps = _load()["jobs"]["sync"]["steps"]
    commit_run = steps[_step_index(steps, "Commit and push")]["run"]
    assert "site/dict/words_uk.txt" in commit_run, (
        "a rebuilt list that is never staged leaves the PR as inconsistent as before"
    )
