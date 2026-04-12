"""Two-pass sync driver for the sync-subtitles PR workflow.

Given a base git SHA and a list of changed transcript/SRT paths, this
script runs the reverse-then-forward sync that the workflow used to do
in bash:

  Step A (SRT → transcript): for each changed uk.srt, diff it against
  the base-SHA version and apply the text changes to transcript_uk.txt
  in-place. Accumulates across all changed SRTs in a talk.

  Step B (transcript → SRT): for each video in each affected talk,
  diff the (possibly Step-A-updated) transcript against a per-video
  effective-old baseline and apply the result to that video's uk.srt.

The per-video effective-old baseline is the key fix for mixed PRs
(transcript edited AND a uk.srt edited in the same commit). Without
it, Step B would try to match the BASE transcript's text in the
already-edited SRT — find_paragraph_blocks fails because the old text
is no longer there. With it, each video gets a baseline that matches
its current SRT state: base_transcript + that video's own Step A
edits, which is exactly what the SRT now represents. The diff that
Step B then applies contains only the work Step A couldn't already
do for that video (direct transcript edits and other videos' SRT
edits, which still need to propagate here).

Invocation:
    python -m tools.sync_pr --base-sha $BASE_SHA

The tool reads `git diff --name-only $BASE_SHA HEAD` itself so the
workflow doesn't need to pre-filter. Exits 0 on success, 1 on any
sync/validate failure (with a GitHub Actions ::error:: line per
failure). Intentionally mutates the working tree (the workflow then
commits whatever changed).
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from .config import OptimizeConfig
from .optimize_srt import optimize
from .sync_srt_to_transcript import sync_srt_to_transcript
from .sync_transcript_to_srt import sync_transcript
from .validate_subtitles import validate as validate_subtitles


def _gha_error(msg: str) -> None:
    print(f"::error::{msg}", file=sys.stderr)


def _run_git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return result.stdout


def _list_changed(base_sha: str) -> list[str]:
    try:
        out = _run_git("diff", "--name-only", base_sha, "HEAD")
    except subprocess.CalledProcessError as exc:
        _gha_error(f"git diff failed: {exc.stderr}")
        return []
    return [line for line in out.splitlines() if line.strip()]


def _show_base(base_sha: str, path: str, dest: Path) -> bool:
    """Write the base-SHA version of `path` to `dest`. Returns False if
    the file didn't exist at base (e.g. newly added in the PR)."""
    try:
        data = subprocess.run(
            ["git", "show", f"{base_sha}:{path}"],
            capture_output=True,
            check=True,
        ).stdout
    except subprocess.CalledProcessError:
        return False
    dest.write_bytes(data)
    return True


def _list_video_slugs(meta_path: Path) -> list[str]:
    if not meta_path.exists():
        return []
    with meta_path.open(encoding="utf-8") as f:
        meta = yaml.safe_load(f) or {}
    return [v["slug"] for v in meta.get("videos", []) if "slug" in v]


def _classify(changed: list[str]) -> tuple[dict[str, list[str]], dict[str, bool]]:
    """Partition changed files into:
      talks_with_srt_edits: {talk_dir: [srt_path, ...]}
      talks_with_transcript_edit: {talk_dir: True}
    Returns both maps. A talk can appear in either or both.
    """
    srt_by_talk: dict[str, list[str]] = {}
    transcript_talks: dict[str, bool] = {}
    for path in changed:
        parts = path.split("/")
        if len(parts) < 2 or parts[0] != "talks":
            continue
        talk_dir = "/".join(parts[:2])
        if path.endswith("/transcript_uk.txt") and len(parts) == 3:
            transcript_talks[talk_dir] = True
        elif path.endswith("/final/uk.srt") and len(parts) == 5:
            srt_by_talk.setdefault(talk_dir, []).append(path)
    return srt_by_talk, transcript_talks


def _process_talk(
    talk_dir: str,
    srt_paths: list[str],
    base_sha: str,
    tmp: Path,
) -> bool:
    """Process a single talk. Returns True on success, False on failure.

    Flow:
      1. Snapshot base_transcript → tmp.
      2. For each changed SRT:
         a. Snapshot its base_srt → tmp.
         b. Run sync_srt_to_transcript on the WORKING transcript (accumulating).
         c. Run sync_srt_to_transcript on a COPY of base_transcript (per-video
            effective-old baseline).
      3. For each video in the talk (per meta.yaml):
         a. Pick old_transcript = effective_old_for_video[slug] if it exists,
            else base_transcript.
         b. Run sync_transcript_to_srt(old_transcript, working_transcript).
         c. Optimize if block count changed.
         d. Validate. (Deferred — workflow still runs validate separately.)
    """
    talk_id = Path(talk_dir).name
    transcript_path = Path(talk_dir) / "transcript_uk.txt"
    if not transcript_path.exists():
        print(f"  [{talk_id}] no transcript_uk.txt — skip", file=sys.stderr)
        return True

    base_transcript = tmp / f"{talk_id}.base_transcript.txt"
    if not _show_base(base_sha, str(transcript_path), base_transcript):
        print(f"  [{talk_id}] transcript is new in this PR — skip", file=sys.stderr)
        return True

    # Step A: propagate each changed SRT's edits onto the real transcript AND
    # onto a per-video copy of the base transcript (effective-old baseline).
    effective_old: dict[str, Path] = {}
    step_a_failed = False
    for srt in srt_paths:
        video_slug = srt.split("/")[2]
        base_srt = tmp / f"{talk_id}__{video_slug}.base.srt"
        if not _show_base(base_sha, srt, base_srt):
            print(f"  [{talk_id}/{video_slug}] SRT is new in this PR — skip", file=sys.stderr)
            continue

        print(f"  [{talk_id}/{video_slug}] SRT → transcript (accumulate)", file=sys.stderr)
        result = sync_srt_to_transcript(
            old_srt=str(base_srt),
            new_srt=srt,
            transcript=str(transcript_path),
        )
        if "error" in result:
            _gha_error(f"{srt}: {result['error']}")
            step_a_failed = True
            continue

        # Per-video baseline: apply this SRT's diff to a fresh copy of
        # base_transcript. The result is what the transcript would look
        # like if THIS video's SRT edits were the only change — exactly
        # what find_paragraph_blocks needs to match against the already-
        # edited SRT in Step B.
        effective = tmp / f"{talk_id}__{video_slug}.effective_old.txt"
        shutil.copyfile(base_transcript, effective)
        baseline_result = sync_srt_to_transcript(
            old_srt=str(base_srt),
            new_srt=srt,
            transcript=str(effective),
        )
        if "error" in baseline_result:
            # Shouldn't normally differ from the accumulate run, but bail
            # loudly if it does.
            _gha_error(f"{srt}: effective-old baseline failed: {baseline_result['error']}")
            step_a_failed = True
            continue
        effective_old[video_slug] = effective

    if step_a_failed:
        return False

    # Step B: sync the (possibly-updated) transcript out to every video's SRT
    # using either the per-video effective-old (for videos whose SRT was
    # edited) or plain base_transcript (for videos whose SRT is untouched).
    meta_path = Path(talk_dir) / "meta.yaml"
    slugs = _list_video_slugs(meta_path)
    if not slugs:
        print(f"  [{talk_id}] meta.yaml has no videos — skip Step B", file=sys.stderr)
        return True

    step_b_failed = False
    for slug in slugs:
        srt_file = Path(talk_dir) / slug / "final" / "uk.srt"
        if not srt_file.exists():
            print(f"  [{talk_id}/{slug}] no uk.srt — skip", file=sys.stderr)
            continue

        old_transcript = effective_old.get(slug, base_transcript)
        baseline_label = "effective-old" if slug in effective_old else "base"
        print(f"  [{talk_id}/{slug}] transcript → SRT (old={baseline_label})", file=sys.stderr)

        result = sync_transcript(
            talk_dir=talk_dir,
            video_slug=slug,
            old_transcript=str(old_transcript),
            new_transcript=str(transcript_path),
        )
        if "error" in result:
            _gha_error(f"{talk_id}/{slug}: {result['error']} — needs full pipeline rebuild")
            step_b_failed = True
            continue

        if result.get("needs_optimize"):
            print(f"  [{talk_id}/{slug}] optimize (block count changed)", file=sys.stderr)
            optimize(
                srt_path=str(srt_file),
                json_path=None,
                output_path=str(srt_file),
                config=OptimizeConfig(skip_duration_split=True, skip_cps_split=True),
            )

        # Validate the updated SRT against the updated transcript. Matches
        # the old bash step's flags: we skip time/duration checks because
        # Step B doesn't touch timecodes (except via optimize, which
        # recomputes them safely).
        print(f"  [{talk_id}/{slug}] validate", file=sys.stderr)
        try:
            passed, _report = validate_subtitles(
                srt_path=str(srt_file),
                transcript_path=str(transcript_path),
                skip_time_check=True,
                skip_duration_check=True,
            )
        except Exception as exc:  # noqa: BLE001
            _gha_error(f"{talk_id}/{slug}: validate raised: {exc}")
            step_b_failed = True
            continue
        if not passed:
            _gha_error(f"{talk_id}/{slug}: validation failed — needs full subtitle rebuild via pipeline")
            step_b_failed = True

    return not step_b_failed


def run(base_sha: str) -> int:
    changed = _list_changed(base_sha)
    srt_by_talk, transcript_talks = _classify(changed)
    all_talks = sorted(set(srt_by_talk) | set(transcript_talks))
    if not all_talks:
        print("No transcript or SRT changes", file=sys.stderr)
        return 0

    tmp = Path("/tmp/sync_pr")
    tmp.mkdir(parents=True, exist_ok=True)

    overall_ok = True
    for talk_dir in all_talks:
        srt_paths = srt_by_talk.get(talk_dir, [])
        talk_id = Path(talk_dir).name
        print("\n========================================", file=sys.stderr)
        print(f"  {talk_id}", file=sys.stderr)
        print("========================================", file=sys.stderr)
        ok = _process_talk(talk_dir, srt_paths, base_sha, tmp)
        overall_ok = overall_ok and ok

    return 0 if overall_ok else 1


def main() -> None:
    p = argparse.ArgumentParser(description="Two-pass sync driver for sync-subtitles PRs")
    p.add_argument("--base-sha", required=True, help="Base SHA of the PR to diff against")
    args = p.parse_args()
    sys.exit(run(args.base_sha))


if __name__ == "__main__":
    main()
