"""Structural guards for workflow defects found by the 2026-07-02 audit.

Workflows can't be executed in the test suite, so these tests pin the
YAML structure the same way test_pipeline_talk_id_normalization does.
"""

import re
from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def test_commit_job_places_glossary_json() -> None:
    """The 'Record glossary version' step writes talks/<id>/glossary.json and
    the translation artifact carries it, but the commit job's placement loop
    used to copy only transcript_uk.txt + review_report.md — leaving
    glossary.json dead end-to-end. Every translation placement loop must
    include glossary.json."""
    text = (WORKFLOWS / "subtitle-pipeline.yml").read_text(encoding="utf-8")
    loops = re.findall(r"for f in ([^;]*transcript_uk\.txt[^;]*); do", text)
    assert loops, "no translation placement loops found"
    for loop in loops:
        assert "glossary.json" in loop, f"placement loop misses glossary.json: for f in {loop}"


def test_whisper_pip_version_spec_is_quoted() -> None:
    """`pip install faster-whisper>=1.2.1` unquoted is a shell redirection:
    the real command is `pip install faster-whisper` with stdout sent to a
    file named '=1.2.1' — the version floor silently vanishes."""
    text = (WORKFLOWS / "whisper.yml").read_text(encoding="utf-8")
    for line in text.splitlines():
        if "pip install" in line and "faster-whisper" in line:
            spec = line.strip()
            assert re.search(r"['\"]faster-whisper>=[^'\"]+['\"]", spec), (
                f"unquoted version spec (shell redirect): {spec}"
            )


def test_commit_job_places_build_manifest() -> None:
    """build_manifest.yaml is written during build, uploaded in the subtitles
    artifact, and listed in the bot-pr patterns — but the commit job's
    subtitle placement filter used to omit it, so it was never committed and
    sync_pr fell back to whisper-strict validation for en-srt talks."""
    text = (WORKFLOWS / "subtitle-pipeline.yml").read_text(encoding="utf-8")
    # the commit job's placement find is the one that also copies build_report.txt
    finds = [line for line in text.splitlines() if "find /tmp/subtitles" in line and "build_report.txt" in line]
    assert finds, "commit-job subtitle placement find not found"
    for line in finds:
        assert "build_manifest.yaml" in line, f"subtitle placement filter misses build_manifest.yaml: {line.strip()}"


def test_commit_job_gates_translation_on_translate_success() -> None:
    """The translate job has a hard verification gate (1:1 paragraph count);
    its artifact is uploaded even on failure so partial progress is
    inspectable. The commit job must NOT place a failed-verify transcript
    into talks/ — that would push a broken baseline to main (the same reason
    BUILD_RESULT gates the subtitle copy)."""
    text = (WORKFLOWS / "subtitle-pipeline.yml").read_text(encoding="utf-8")
    placement = re.search(r"- name: Place artifacts into talk directories.*?- name: ", text, re.S)
    assert placement, "placement step not found"
    step = placement.group(0)
    assert "TRANSLATE_RESULT" in step, "translation placement is not gated on translate-and-review result"


def test_review_issue_requires_built_subtitles() -> None:
    """The review tracking issue used to be created/reset to review:pending
    even when build-timecodes failed and the run committed no subtitles —
    if: success() only covers the commit job's own steps."""
    text = (WORKFLOWS / "subtitle-pipeline.yml").read_text(encoding="utf-8")
    start = text.find("- name: Create review tracking issue")
    assert start != -1, "issue step not found"
    nxt = text.find("- name: ", start + 1)
    step = text[start : nxt if nxt != -1 else len(text)]
    assert "needs.build-timecodes.result == 'success'" in step, "issue step does not require build-timecodes success"


def _ci_watched_paths() -> str:
    """The path list the CI lanes are gated on.

    It used to be the `paths:` filter on ci.yml's triggers. A filtered trigger
    cannot coexist with a required check (no run means no `gate` to wait on),
    so the list moved into the `changes` job — see tests/test_ci_gate.py. The
    guards below still hold; they just read it where it now lives.
    """
    data = yaml.safe_load((WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))
    detect = next(s for s in data["jobs"]["changes"]["steps"] if s.get("id") == "detect")
    return detect["run"]


def test_ci_paths_cover_precommit_config() -> None:
    """tests/test_ruff_pin_lockstep.py exists to catch a ruff bump in ONE of
    its three pinned places — but ci.yml's path filters omitted
    .pre-commit-config.yaml, so a PR bumping only the pre-commit rev never
    ran CI (and never ran the guard)."""
    paths = _ci_watched_paths()
    assert "'.pre-commit-config.yaml'" in paths, f"watched paths miss .pre-commit-config.yaml: {paths}"


def test_ci_paths_cover_shipped_talk_data_guards() -> None:
    """The suite has shipped-data guards (test_no_plaintext_vimeo, and
    test_schemas' all-shipped meta.yaml/whisper.json validation) — but ci.yml
    used to skip entirely on PRs that only touch talks/**, so a hand edit
    reintroducing a plaintext vimeo_url or a corrupt whisper.json shipped
    with no check running at all."""
    paths = _ci_watched_paths()
    assert "'talks/*/meta.yaml'" in paths, f"watched paths miss talks/*/meta.yaml: {paths}"
    assert "'talks/*/*/source/whisper.json'" in paths, f"watched paths miss whisper.json: {paths}"


def test_sync_review_status_unlabeled_checks_removed_label() -> None:
    """For an 'unlabeled' event github.event.issue.labels reflects the state
    AFTER removal, so removing the last review:* label used to skip the sync
    and leave review-status.json stale. The job gate must also look at the
    removed label itself (github.event.label.name)."""
    data = yaml.safe_load((WORKFLOWS / "sync-review-status.yml").read_text(encoding="utf-8"))
    cond = data["jobs"]["sync"]["if"]
    assert "github.event.label.name" in cond, f"gate ignores the removed label: {cond}"


def test_sync_subtitles_skips_draft_prs() -> None:
    """A draft PR is work-in-progress: the author is still editing the
    transcript/SRT, so the bot must not race in, sync, and commit back over
    half-finished edits. The sync job gates on the PR not being a draft, and
    the trigger adds `ready_for_review` so marking a draft ready fires exactly
    one sync (the default types don't include that transition)."""
    data = yaml.safe_load((WORKFLOWS / "sync-subtitles.yml").read_text(encoding="utf-8"))
    on = data.get("on") or data.get(True)  # yaml 1.1 parses bare `on` as True
    types = on["pull_request"].get("types") or []
    assert "ready_for_review" in types, (
        f"pull_request.types must include ready_for_review so a draft->ready transition triggers the sync: {types}"
    )
    cond = data["jobs"]["sync"]["if"]
    assert "draft" in cond, f"sync job must skip draft PRs via an `if` gate: {cond}"


def test_sync_subtitles_commit_skips_ci_to_avoid_self_trigger() -> None:
    """The sync job commits the synced uk.srt/transcript as github-actions[bot]
    and pushes to the PR branch. That push re-triggers this same pull_request
    workflow (its paths include final/uk.srt); the second run then sees BOTH
    transcript and SRT changed vs the PR base and runs the reverse
    SRT->transcript pass, which conflicts with the already-applied edit and
    fails red. The bot's own sync commit must carry a skip-ci token so it does
    not recursively trigger the workflow."""
    text = (WORKFLOWS / "sync-subtitles.yml").read_text(encoding="utf-8")
    commit_lines = [line for line in text.splitlines() if "git commit -m" in line]
    assert commit_lines, "no `git commit -m` line found in sync-subtitles.yml"
    skip_token = re.compile(r"\[(?:skip ci|ci skip|no ci|skip actions|actions skip)\]")
    for line in commit_lines:
        assert skip_token.search(line), f"sync commit message lacks a skip-ci token (self-trigger risk): {line.strip()}"


def test_ytdlp_steps_decode_video_ref_to_player_url() -> None:
    """Vimeo answers 401 on the internal API yt-dlp uses for the canonical
    `vimeo.com/<id>/<hash>` form (whisper runs 2026-07-27 downloaded nothing).
    Every workflow that feeds a decoded video_ref to yt-dlp must ask for the
    `player.vimeo.com` embed form, which still resolves."""
    for name in ("whisper.yml", "new-talk.yml"):
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        decodes = re.findall(r"python3 -m tools\.vimeo_codec decode ([^\n]*)", text)
        assert decodes, f"{name}: no video_ref decode found"
        for call in decodes:
            assert "--player" in call, f"{name}: yt-dlp needs the embed form: decode {call}"


def test_review_issue_is_only_touched_on_main() -> None:
    """The review tracking issue is main-scoped shared state: creating it —
    or resetting an approved one back to review:pending — announces that new
    subtitles are on main and ready to review.

    A run dispatched from a feature branch commits its artifacts to that
    branch (see bot-pr.sh), so nothing reached main and the issue must be
    left alone. Regression guard for the 2026-07-31 branch-dispatch fallout.
    """
    wf = yaml.safe_load((WORKFLOWS / "subtitle-pipeline.yml").read_text(encoding="utf-8"))
    steps = wf["jobs"]["commit"]["steps"]
    issue_steps = [s for s in steps if "review tracking issue" in (s.get("name") or "").lower()]
    assert issue_steps, "review tracking issue step not found"
    for step in issue_steps:
        cond = str(step.get("if", ""))
        assert "github.ref_name == 'main'" in cond, f"review-issue step must be gated on main, got if: {cond!r}"


def test_review_issue_reset_keeps_a_claimed_review_claimed() -> None:
    """A rebuild invalidates an approval, but never a claim.

    The reset dropped `review:in-progress` unconditionally while leaving the
    assignee in place, so a talk rebuilt after someone claimed it went back to
    `review:pending` — and the SPA, which reads the label via
    review-status.json, advertised it as needing a reviewer while that
    reviewer was still on it. Observed on issue #895: assigned 2026-07-27,
    reset by the 2026-07-30 rebuild.

    An assigned issue must therefore land on `review:in-progress`; only an
    unassigned one resets to `review:pending`.
    """
    wf = yaml.safe_load((WORKFLOWS / "subtitle-pipeline.yml").read_text(encoding="utf-8"))
    step = next(s for s in wf["jobs"]["commit"]["steps"] if "review tracking issue" in (s.get("name") or "").lower())
    run = step["run"]
    # The reset branch only — everything between the existing-issue test and
    # the `else` that creates a fresh issue (which is pending by definition).
    start = run.find('if [ -n "$EXISTING" ]')
    assert start != -1, "existing-issue branch not found"
    reset = run[start : run.find("\n          else", start)]
    assert "--json assignees" in reset, "reset must read the issue's assignees before picking a label"
    assert '--add-label "review:pending' not in reset.replace("'", '"'), (
        "reset must not unconditionally re-apply review:pending — an assigned issue stays in-progress"
    )
    assert "review:in-progress" in reset, "reset must be able to land on review:in-progress"
