"""Generate project statistics as docs/stats.json.

Walks talks/ directory, parses report.txt and review-status.json
to produce aggregate and per-talk stats for the SPA dashboard.

Usage:
    python -m tools.generate_stats [--output docs/stats.json]
"""

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import yaml


def parse_report(report_path):
    """Extract stats from a validation report.txt file."""
    text = report_path.read_text(encoding="utf-8")
    stats = {}
    m = re.search(r"Total blocks:\s*(\d+)", text)
    if m:
        stats["blocks"] = int(m.group(1))
    m = re.search(r"CPS:\s*avg=([\d.]+).*?max=([\d.]+)", text)
    if m:
        stats["cps_avg"] = float(m.group(1))
        stats["cps_max"] = float(m.group(2))
    m = re.search(r"CPL:\s*avg=([\d.]+).*?max=(\d+)", text)
    if m:
        stats["cpl_avg"] = float(m.group(1))
        stats["cpl_max"] = int(m.group(2))
    return stats


def generate_stats(talks_dir, review_status_path, output_path):
    """Generate stats.json from repo data."""
    talks_dir = Path(talks_dir)
    review_status = {}
    if Path(review_status_path).exists():
        with open(review_status_path, encoding="utf-8") as f:
            review_status = json.load(f).get("talks", {})

    talks = []
    totals = {
        "talks": 0,
        "with_en": 0,
        "with_uk": 0,
        "with_srt": 0,
        "approved": 0,
        "pending": 0,
        "in_progress": 0,
    }

    for meta_path in sorted(talks_dir.glob("*/meta.yaml")):
        talk_dir = meta_path.parent
        talk_id = talk_dir.name

        with open(meta_path, encoding="utf-8") as f:
            meta = yaml.safe_load(f) or {}

        totals["talks"] += 1
        has_en = (talk_dir / "transcript_en.txt").exists()
        has_uk = (talk_dir / "transcript_uk.txt").exists()
        if has_en:
            totals["with_en"] += 1
        if has_uk:
            totals["with_uk"] += 1

        # Review status
        rs = review_status.get(talk_id, {})
        status = rs.get("status")
        if status == "approved":
            totals["approved"] += 1
        elif status == "in-progress":
            totals["in_progress"] += 1
        elif status == "pending":
            totals["pending"] += 1

        # Glossary version
        glossary = {}
        gj = talk_dir / "glossary.json"
        if gj.exists():
            glossary = json.loads(gj.read_text(encoding="utf-8"))

        # Per-video stats
        videos = []
        for v in meta.get("videos", []):
            slug = v.get("slug", "")
            video_dir = talk_dir / slug
            has_srt = (video_dir / "final" / "uk.srt").exists()
            video_stats = {"slug": slug, "has_srt": has_srt}

            report = video_dir / "final" / "report.txt"
            if report.exists():
                video_stats.update(parse_report(report))

            videos.append(video_stats)

        if any(v["has_srt"] for v in videos):
            totals["with_srt"] += 1

        talks.append(
            {
                "id": talk_id,
                "title": meta.get("title", talk_id),
                "date": str(meta.get("date", talk_id[:10])),
                "has_en": has_en,
                "has_uk": has_uk,
                "review_status": status,
                "glossary": glossary,
                "videos": videos,
            }
        )

    output = {
        "generated_at": datetime.now(UTC).isoformat(),
        "totals": totals,
        "talks": talks,
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(
        f"Stats: {totals['talks']} talks, {totals['with_uk']} translated, "
        f"{totals['with_srt']} with SRT, {totals['approved']} approved"
    )
    return output


def main():
    parser = argparse.ArgumentParser(description="Generate project statistics")
    parser.add_argument("--talks-dir", default="talks", help="Path to talks directory")
    parser.add_argument("--review-status", default="review-status.json", help="Path to review-status.json")
    parser.add_argument("--output", default="stats.json", help="Output path")
    args = parser.parse_args()
    generate_stats(args.talks_dir, args.review_status, args.output)


if __name__ == "__main__":
    main()
