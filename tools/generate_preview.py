"""Generate GitHub Pages preview site for subtitle review.

Each video gets a self-contained HTML page with:
- Vimeo embedded player
- JavaScript-driven SRT subtitle overlay
- No external dependencies beyond Vimeo Player SDK

Usage:
    python -m tools.generate_preview --talk-dir talks/TALK --output-dir /tmp/site
    python -m tools.generate_preview --scan-dir /tmp/site --index-only --output-dir /tmp/site
"""

import argparse
import html
import re
import sys
from pathlib import Path

import yaml


def vimeo_url_to_embed(url: str) -> str:
    """Convert vimeo.com URL to player embed URL."""
    m = re.match(r"https?://vimeo\.com/(\d+)/([a-f0-9]+)", url)
    if m:
        return f"https://player.vimeo.com/video/{m.group(1)}?h={m.group(2)}"
    return url


def get_srt_parser_js() -> str:
    """Read the shared JS SRT parser."""
    js_path = Path(__file__).parent / "preview_srt_parser.js"
    return js_path.read_text(encoding="utf-8")


def generate_video_page(
    talk_title: str,
    video_title: str,
    vimeo_embed_url: str,
    srt_content: str,
    base_url: str = "",
) -> str:
    """Generate a self-contained HTML preview page for one video."""
    parser_js = get_srt_parser_js()
    # In <script type="text/plain">, content is not parsed as HTML.
    # Only need to prevent </script> from closing the tag early.
    safe_srt = srt_content.replace("</script>", "<\\/script>")

    return f"""<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(video_title)} – {html.escape(talk_title)}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: #1a1a1a; color: #fff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
.header {{ padding: 12px 20px; background: #111; }}
.header h1 {{ font-size: 16px; font-weight: normal; color: #aaa; }}
.header h2 {{ font-size: 14px; font-weight: normal; color: #666; margin-top: 4px; }}
.header a {{ color: #6af; text-decoration: none; }}
.player-container {{ position: relative; width: 100%; max-width: 960px; margin: 20px auto; }}
.video-wrap {{ position: relative; padding-bottom: 56.25%; height: 0; }}
.video-wrap iframe {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: 0; }}
#subtitle-overlay {{
  position: relative;
  width: 100%;
  min-height: 60px;
  padding: 12px 16px;
  background: rgba(0, 0, 0, 0.85);
  color: #fff;
  font-size: 20px;
  line-height: 1.4;
  text-align: center;
  border-radius: 0 0 4px 4px;
}}
#subtitle-overlay:empty {{ min-height: 20px; }}
#subtitle-overlay:empty::after {{ content: '\\200B'; }}
.time-display {{
  text-align: center;
  padding: 8px;
  color: #666;
  font-size: 13px;
  font-family: monospace;
}}
</style>
</head>
<body>
<div class="header">
  <h1><a href="{base_url}/">&larr; Index</a> &middot; {html.escape(talk_title)}</h1>
  <h2>{html.escape(video_title)}</h2>
</div>
<div class="player-container">
  <div class="video-wrap">
    <iframe id="vimeo-player"
      src="{html.escape(vimeo_embed_url)}&texttrack=false"
      allow="autoplay; fullscreen" allowfullscreen></iframe>
  </div>
  <div id="subtitle-overlay"></div>
  <div class="time-display" id="time-display">00:00:00</div>
</div>

<script id="srt-data" type="text/plain">{safe_srt}</script>

<script src="https://player.vimeo.com/api/player.js"></script>
<script>
{parser_js}

(function() {{
  var srtText = document.getElementById('srt-data').textContent;
  var subtitles = parseSRT(srtText);
  var overlay = document.getElementById('subtitle-overlay');
  var timeDisplay = document.getElementById('time-display');
  var iframe = document.getElementById('vimeo-player');
  var player = new Vimeo.Player(iframe);
  var lastText = '';

  player.on('timeupdate', function(data) {{
    var ms = Math.round(data.seconds * 1000);
    var active = findActiveSubtitle(subtitles, ms);
    var text = active ? active.text : '';
    if (text !== lastText) {{
      overlay.textContent = text;
      lastText = text;
    }}
    var s = Math.floor(data.seconds);
    var h = String(Math.floor(s / 3600)).padStart(2, '0');
    var m = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
    var sec = String(s % 60).padStart(2, '0');
    timeDisplay.textContent = h + ':' + m + ':' + sec;
  }});
}})();
</script>
</body>
</html>"""


def generate_index_page(entries: list, base_url: str = "") -> str:
    """Generate index page listing all available previews."""
    rows = []
    for e in sorted(entries, key=lambda x: x.get("date", "")):
        link = f"{base_url}/{e['talk_id']}/{e['video_slug']}/"
        rows.append(
            f"<tr><td>{html.escape(e.get('date', ''))}</td>"
            f'<td><a href="{link}">{html.escape(e.get("talk_title", e["talk_id"]))}</a></td>'
            f"<td>{html.escape(e.get('video_title', e['video_slug']))}</td></tr>"
        )

    table = "\n".join(rows) if rows else "<tr><td colspan=3>No previews yet</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Subtitle Preview</title>
<style>
body {{ background: #1a1a1a; color: #fff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 20px; }}
h1 {{ font-size: 20px; margin-bottom: 16px; }}
table {{ border-collapse: collapse; width: 100%; max-width: 800px; }}
th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid #333; }}
th {{ color: #888; font-size: 13px; }}
a {{ color: #6af; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<h1>Subtitle Preview</h1>
<table>
<tr><th>Date</th><th>Talk</th><th>Video</th></tr>
{table}
</table>
</body>
</html>"""


def generate_site(talk_dir: str, output_dir: str, base_url: str = "", video_slug: str | None = None):
    """Generate preview pages for a talk."""
    talk_path = Path(talk_dir)
    out = Path(output_dir)

    meta_file = talk_path / "meta.yaml"
    if not meta_file.exists():
        print(f"No meta.yaml in {talk_path}", file=sys.stderr)
        return []

    with open(meta_file) as f:
        meta = yaml.safe_load(f)

    talk_title = meta.get("title", talk_path.name)
    talk_id = talk_path.name
    date = meta.get("date", talk_id[:10])
    entries = []

    for v in meta.get("videos", []):
        slug = v["slug"]
        if video_slug and slug != video_slug:
            continue
        srt_path = talk_path / slug / "final" / "uk.srt"
        if not srt_path.exists():
            print(f"  Skip {slug}: no uk.srt", file=sys.stderr)
            continue

        vimeo_url = v.get("vimeo_url", "")
        embed_url = vimeo_url_to_embed(vimeo_url)
        srt_content = srt_path.read_text(encoding="utf-8")
        vtitle = v.get("title", slug)

        page_html = generate_video_page(talk_title, vtitle, embed_url, srt_content, base_url)

        page_dir = out / talk_id / slug
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(page_html, encoding="utf-8")
        print(f"  Generated: {talk_id}/{slug}/index.html", file=sys.stderr)

        entries.append(
            {
                "talk_id": talk_id,
                "talk_title": talk_title,
                "video_slug": slug,
                "video_title": vtitle,
                "date": str(date),
            }
        )

    return entries


def scan_existing_previews(site_dir: str) -> list:
    """Scan existing preview site for index generation."""
    entries = []
    site = Path(site_dir)
    for index_html in site.rglob("index.html"):
        parts = index_html.relative_to(site).parts
        if len(parts) == 3:  # talk_id/video_slug/index.html
            talk_id, video_slug = parts[0], parts[1]
            entries.append(
                {
                    "talk_id": talk_id,
                    "talk_title": talk_id,
                    "video_slug": video_slug,
                    "video_title": video_slug,
                    "date": talk_id[:10],
                }
            )
    return entries


def main():
    p = argparse.ArgumentParser(description="Generate subtitle preview site")
    p.add_argument("--talk-dir", help="Talk directory to generate preview for")
    p.add_argument("--video-slug", help="Generate for specific video only")
    p.add_argument("--output-dir", required=True, help="Output directory for HTML files")
    p.add_argument("--base-url", default="", help="Base URL for links (e.g. /sy-subtitles)")
    p.add_argument("--scan-dir", help="Scan existing site directory for index")
    p.add_argument("--index-only", action="store_true", help="Only regenerate index page")
    args = p.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    entries = []

    if args.talk_dir and not args.index_only:
        entries = generate_site(args.talk_dir, args.output_dir, args.base_url, args.video_slug)

    if args.scan_dir:
        entries = scan_existing_previews(args.scan_dir)

    # Always write index
    index_html = generate_index_page(entries, args.base_url)
    (out / "index.html").write_text(index_html, encoding="utf-8")
    print(f"Index: {out}/index.html ({len(entries)} entries)", file=sys.stderr)


if __name__ == "__main__":
    main()
