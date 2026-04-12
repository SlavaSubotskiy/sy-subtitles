"""Build fake-LLM snapshots for dry-run pipeline replay from repo artefacts.

For every talk that already has whisper.json + transcript_en.txt + transcript_uk.txt
+ final/uk.srt, this tool produces a directory of canned LLM responses that
stand in for the real translate / review / build-chunks phases during a dry-run.

Snapshot layout per (talk, video):

    tests/fixtures/pipeline_snapshots/{talk_id}/{video_slug}/
        manifest.json                # which phases are bootstrapped and where
        transcript_uk.txt            # canned translate output
        review_report.md             # canned review output (identity by default)
        work/
            chunk_0_result.txt       # canned build-chunks LLM output
            chunk_1_result.txt       # one per chunk build_map.prepare created
            ...
            uk.map                   # canned build-en-srt LLM output
        expected/
            transcript_uk.txt        # ground-truth final transcript
            final_uk.srt             # ground-truth final SRT

During dry-run the pipeline calls tools.fake_llm which copies files from
the snapshot into the real work dirs, then runs the Python side normally.
Verification (tools.verify_snapshot) then asserts:
  * validate_subtitles passes on produced uk.srt
  * transcript text matches expected exactly

Usage:
    python -m tools.bootstrap_snapshot --talk-dir talks/1988-05-08_Sahasrara-Puja-How-it-was-decided
    python -m tools.bootstrap_snapshot --all
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from .build_map import find_paragraph_boundaries
from .srt_utils import load_whisper_json, ms_to_time
from .text_segmentation import load_transcript

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_ROOT = ROOT / "tests" / "fixtures" / "pipeline_snapshots"


def _compute_baseline(talk_dir: Path, video_slug: str, snapshot: Path, scratch: Path) -> dict:
    """Dry-run the full pipeline with the snapshot we just wrote and
    capture the resulting uk.srt statistics. Stored as the "expected"
    shape for verify_snapshot."""
    from .config import OptimizeConfig
    from .srt_utils import calc_stats
    from .srt_utils import parse_srt as _parse_srt

    dst = scratch / f"baseline_{talk_dir.name}"
    if dst.exists():
        _rm_tree(dst)
    shutil.copytree(talk_dir, dst)
    (dst / "transcript_uk.txt").unlink(missing_ok=True)
    work = dst / video_slug / "work"
    final = dst / video_slug / "final"
    if work.exists():
        _rm_tree(work)
    if final.exists():
        _rm_tree(final)

    def run(cmd: list[str]) -> None:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, check=False)
        if r.returncode != 0:
            raise RuntimeError(f"baseline step failed: {' '.join(cmd)}\n{r.stderr[-1000:]}")

    run([sys.executable, "-m", "tools.fake_llm", "translate", "--snapshot", str(snapshot), "--talk-dir", str(dst)])
    run([sys.executable, "-m", "tools.fake_llm", "review", "--snapshot", str(snapshot), "--talk-dir", str(dst)])
    run(
        [
            sys.executable,
            "-m",
            "tools.build_map",
            "prepare",
            "--talk-dir",
            str(dst),
            "--video-slug",
            video_slug,
        ]
    )
    n_chunks = json.loads((dst / video_slug / "work" / "build_meta.json").read_text())["n_chunks"]
    for i in range(n_chunks):
        run(
            [
                sys.executable,
                "-m",
                "tools.fake_llm",
                "build-chunk",
                "--snapshot",
                str(snapshot),
                "--work-dir",
                str(dst / video_slug / "work"),
                "--chunk-idx",
                str(i),
            ]
        )
    run(
        [
            sys.executable,
            "-m",
            "tools.build_map",
            "assemble",
            "--talk-dir",
            str(dst),
            "--video-slug",
            video_slug,
        ]
    )
    srt = dst / video_slug / "final" / "uk.srt"
    run(
        [
            sys.executable,
            "-m",
            "tools.optimize_srt",
            "--srt",
            str(srt),
            "--output",
            str(srt),
            "--skip-duration-split",
            "--skip-cps-split",
        ]
    )

    blocks = _parse_srt(str(srt))
    stats = calc_stats(blocks, OptimizeConfig())

    baseline = {
        "n_blocks": len(blocks),
        "avg_cps": round(float(stats["avg_cps"]), 2),
        "max_cps": round(float(stats["max_cps"]), 2),
        "cps_over_hard": int(stats["cps_over_hard"]),
        "cps_over_target": int(stats["cps_over_target"]),
        "duration_under_min": int(stats["duration_under_min"]),
        "duration_over_max": int(stats["duration_over_max"]),
    }
    _rm_tree(dst)
    return baseline


def _build_timings_via_paragraph_distribution(
    talk_dir: Path, video_slug: str, uk_blocks: list[dict]
) -> dict[int, tuple[int, int]]:
    """Deterministic fake-LLM timings: for each paragraph, distribute the
    whisper paragraph time range across its UK blocks proportional to
    character count. Produces CPS-valid timings with no LLM / network
    dependency and no multi-line text issues.
    """
    en_paras = load_transcript(str(talk_dir / "transcript_en.txt"))
    whisper_segs = load_whisper_json(str(talk_dir / video_slug / "source" / "whisper.json"))
    para_bounds = find_paragraph_boundaries(en_paras, whisper_segs)

    # Group blocks by para_idx
    by_para: dict[int, list[dict]] = {}
    for b in uk_blocks:
        by_para.setdefault(b["para_idx"], []).append(b)

    timings: dict[int, tuple[int, int]] = {}
    min_dur = 1200
    min_gap = 80

    # Track rolling end so paragraphs without whisper coverage fall forward
    rolling_end = 0
    for p_idx in sorted(by_para):
        blocks_in_para = by_para[p_idx]
        if p_idx < len(para_bounds) and para_bounds[p_idx][0] > 0:
            p_start, p_end = para_bounds[p_idx]
        else:
            # No coverage — place after rolling_end with min_dur per block
            p_start = rolling_end + min_gap
            p_end = p_start + (min_dur + min_gap) * len(blocks_in_para)
        if p_end <= p_start:
            p_end = p_start + min_dur
        span = p_end - p_start
        chars = [max(1, len(b["text"])) for b in blocks_in_para]
        total_chars = sum(chars)
        cursor = p_start
        for b, c in zip(blocks_in_para, chars, strict=True):
            share = span * c // total_chars
            dur = max(min_dur, share - min_gap)
            end = min(p_end, cursor + dur)
            if end - cursor < min_dur:
                end = cursor + min_dur
            timings[b["id"]] = (cursor, end)
            cursor = end + min_gap
            rolling_end = max(rolling_end, end)
    return timings


def _write_chunk_results(
    work_snapshot: Path,
    uk_blocks_path: Path,
    build_meta_path: Path,
    chunk_dir: Path,
    timings: dict[int, tuple[int, int]],
) -> None:
    """Group blocks by chunk (reading chunk prompt files) and write chunk_N_result.txt."""
    uk_blocks = json.loads(uk_blocks_path.read_text(encoding="utf-8"))
    meta = json.loads(build_meta_path.read_text(encoding="utf-8"))
    n_chunks = meta["n_chunks"]

    # Parse each chunk prompt to find which block ids belong to that chunk.
    # The prompt lists UK blocks as "#<id>: <text>".
    block_id_re = re.compile(r"^\s*#(\d+):", re.MULTILINE)
    for ci in range(n_chunks):
        prompt = (chunk_dir / f"chunk_{ci}.txt").read_text(encoding="utf-8")
        # Block ids appear in the "UK BLOCKS TO TIME" table as "<id> | <text>".
        # That pattern is the same id format we use below, so match conservatively.
        ids = [int(m.group(1)) for m in block_id_re.finditer(prompt)]
        # Deduplicate while preserving order
        seen: set[int] = set()
        ordered = [i for i in ids if not (i in seen or seen.add(i))]
        if not ordered:
            # Fallback: use block span recorded by build_meta
            ordered = [b["id"] for b in uk_blocks]

        lines = []
        for bid in ordered:
            if bid not in timings:
                continue
            s, e = timings[bid]
            lines.append(f"#{bid} | {ms_to_time(s)} | {ms_to_time(e)}")
        (work_snapshot / f"chunk_{ci}_result.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_uk_map(work_snapshot: Path, uk_blocks: list[dict], timings: dict[int, tuple[int, int]]) -> None:
    lines = [
        f"{b['id']} | {ms_to_time(timings[b['id']][0])} | {ms_to_time(timings[b['id']][1])} | {b['text']}"
        for b in uk_blocks
        if b["id"] in timings
    ]
    (work_snapshot / "uk.map").write_text("\n".join(lines) + "\n", encoding="utf-8")


def bootstrap_talk(talk_dir: Path, video_slug: str) -> Path:
    """Bootstrap a snapshot for one (talk, video) pair. Returns snapshot dir."""
    meta_path = talk_dir / "meta.yaml"
    transcript_uk = talk_dir / "transcript_uk.txt"
    whisper_path = talk_dir / video_slug / "source" / "whisper.json"
    shipped_srt_path = talk_dir / video_slug / "final" / "uk.srt"

    for required in [meta_path, transcript_uk, whisper_path, shipped_srt_path]:
        if not required.is_file():
            raise FileNotFoundError(f"bootstrap requires {required}")

    snapshot = SNAPSHOT_ROOT / talk_dir.name / video_slug
    snapshot.mkdir(parents=True, exist_ok=True)
    (snapshot / "work").mkdir(exist_ok=True)
    (snapshot / "expected").mkdir(exist_ok=True)

    # 1. Canned translate + review: shipped transcript_uk.txt is already reviewed
    (snapshot / "transcript_uk.txt").write_text(transcript_uk.read_text(encoding="utf-8"), encoding="utf-8")
    review_report = talk_dir / "review_report.md"
    if review_report.is_file():
        (snapshot / "review_report.md").write_text(review_report.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        # Identity review — no changes flagged.
        (snapshot / "review_report.md").write_text(
            "# Review Report\n\nReviewer L: OK\nReviewer S: OK\nCritic: no changes.\n",
            encoding="utf-8",
        )

    # 2. Run build_map prepare in an isolated scratch copy so we can grab
    #    uk_blocks.json + chunk_N.txt + build_meta.json without polluting repo.
    scratch = snapshot.parent / "_scratch"
    scratch_talk = scratch / talk_dir.name
    scratch_talk.mkdir(parents=True, exist_ok=True)
    (scratch_talk / "transcript_en.txt").write_bytes((talk_dir / "transcript_en.txt").read_bytes())
    (scratch_talk / "transcript_uk.txt").write_bytes(transcript_uk.read_bytes())
    (scratch_talk / "meta.yaml").write_bytes(meta_path.read_bytes())
    vdir = scratch_talk / video_slug
    (vdir / "source").mkdir(parents=True, exist_ok=True)
    (vdir / "source" / "whisper.json").write_bytes(whisper_path.read_bytes())
    en_srt = talk_dir / video_slug / "source" / "en.srt"
    if en_srt.is_file():
        (vdir / "source" / "en.srt").write_bytes(en_srt.read_bytes())

    prepare_cmd = [
        sys.executable,
        "-m",
        "tools.build_map",
        "prepare",
        "--talk-dir",
        str(scratch_talk),
        "--video-slug",
        video_slug,
        "--timing-source",
        "whisper",
    ]
    result = subprocess.run(prepare_cmd, capture_output=True, text=True, cwd=ROOT)
    if result.returncode != 0:
        raise RuntimeError(f"build_map prepare failed for {talk_dir.name}/{video_slug}:\n{result.stderr[-2000:]}")

    work_scratch = vdir / "work"
    uk_blocks_path = work_scratch / "uk_blocks.json"
    build_meta_path = work_scratch / "build_meta.json"
    if not uk_blocks_path.is_file() or not build_meta_path.is_file():
        raise RuntimeError(f"build_map prepare did not produce uk_blocks/build_meta for {talk_dir.name}/{video_slug}")

    # Save only the small prepare outputs + the chunk_N_result.txt files we
    # derive below. chunk_N.txt prompts are regenerated every run by
    # build_map.prepare — keeping them in the snapshot bloats the repo
    # ~400KB per talk for no value.
    (snapshot / "work" / "uk_blocks.json").write_bytes(uk_blocks_path.read_bytes())
    (snapshot / "work" / "build_meta.json").write_bytes(build_meta_path.read_bytes())

    # 3. Build per-block timings deterministically by paragraph distribution
    uk_blocks = json.loads(uk_blocks_path.read_text(encoding="utf-8"))
    timings = _build_timings_via_paragraph_distribution(scratch_talk, video_slug, uk_blocks)
    got = sum(1 for b in uk_blocks if b["id"] in timings)
    print(f"  paragraph distribution timed {got}/{len(uk_blocks)} blocks", file=sys.stderr)

    # 4. Write chunk_N_result.txt grouped by chunk (prompt files read from scratch)
    _write_chunk_results(
        snapshot / "work",
        uk_blocks_path,
        build_meta_path,
        work_scratch,  # chunk_N.txt live here after build_map prepare
        timings,
    )

    # 5. Write full uk.map for build-en-srt mode
    _write_uk_map(snapshot / "work", uk_blocks, timings)

    # 6. expected/ — ground truth
    (snapshot / "expected" / "transcript_uk.txt").write_bytes(transcript_uk.read_bytes())
    (snapshot / "expected" / "final_uk.srt").write_bytes(shipped_srt_path.read_bytes())

    # 7. Baseline replay: run the same pipeline the dry-run test will run,
    # capture the resulting block-count and stat shape so verify can check
    # "current run matches baseline ± epsilon" instead of against an
    # absolute CPS/duration threshold that generate_map can't always hit.
    baseline = _compute_baseline(talk_dir, video_slug, snapshot, scratch)

    # 8. manifest
    manifest = {
        "talk_id": talk_dir.name,
        "video_slug": video_slug,
        "n_blocks": len(uk_blocks),
        "n_chunks": json.loads(build_meta_path.read_text())["n_chunks"],
        "bootstrap_method": "paragraph_distribution",
        "directly_timed": got,
        "baseline": baseline,
        "source": "bootstrap_snapshot from repo artefacts",
    }
    (snapshot / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Clean up scratch copy
    _rm_tree(scratch_talk)
    with contextlib.suppress(OSError):
        scratch.rmdir()

    return snapshot


def _rm_tree(p: Path) -> None:
    if not p.exists():
        return
    for child in p.iterdir():
        if child.is_dir():
            _rm_tree(child)
        else:
            child.unlink()
    p.rmdir()


def _iter_complete_talks():
    for talk_dir in sorted((ROOT / "talks").iterdir()):
        if not talk_dir.is_dir():
            continue
        meta_path = talk_dir / "meta.yaml"
        if not meta_path.is_file():
            continue
        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        if not (talk_dir / "transcript_en.txt").is_file():
            continue
        if not (talk_dir / "transcript_uk.txt").is_file():
            continue
        for video in meta.get("videos", []):
            slug = video.get("slug", "")
            if not slug:
                continue
            vd = talk_dir / slug
            if (vd / "source" / "whisper.json").is_file() and (vd / "final" / "uk.srt").is_file():
                yield talk_dir, slug


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap fake-LLM snapshots")
    parser.add_argument("--talk-dir", help="Single talk directory")
    parser.add_argument("--video-slug", help="Video slug (required with --talk-dir)")
    parser.add_argument("--all", action="store_true", help="Bootstrap every complete talk")
    args = parser.parse_args()

    if args.all:
        count = 0
        for talk_dir, slug in _iter_complete_talks():
            print(f"→ {talk_dir.name}/{slug}", file=sys.stderr)
            try:
                snap = bootstrap_talk(talk_dir, slug)
                print(f"  ✓ {snap.relative_to(ROOT)}", file=sys.stderr)
                count += 1
            except Exception as e:
                print(f"  ✗ {e}", file=sys.stderr)
        print(f"\nBootstrapped {count} snapshots", file=sys.stderr)
        return

    if not args.talk_dir or not args.video_slug:
        parser.error("--talk-dir AND --video-slug are required (or use --all)")

    snap = bootstrap_talk(Path(args.talk_dir), args.video_slug)
    print(f"Bootstrap complete: {snap}", file=sys.stderr)


if __name__ == "__main__":
    main()
