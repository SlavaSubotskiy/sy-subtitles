"""Generate GitHub Pages preview site for subtitle review.

Scans all talks with uk.srt and generates:
- Per-video page: Vimeo embed + dynamic SRT fetch from GitHub raw
- Index page listing all available previews

SRT files are NOT embedded — fetched at runtime from main branch.

Usage:
    python -m tools.generate_preview --output-dir /tmp/site
    python -m tools.generate_preview --output-dir /tmp/site --repo SlavaSubotskiy/sy-subtitles
"""

import argparse
import html
import re
import sys
from pathlib import Path

import yaml

GITHUB_RAW = "https://raw.githubusercontent.com"
DEFAULT_REPO = "SlavaSubotskiy/sy-subtitles"
DEFAULT_BRANCH = "main"


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
    srt_raw_url: str,
    base_url: str = "",
) -> str:
    """Generate HTML preview page that fetches SRT dynamically."""
    parser_js = get_srt_parser_js()

    issue_repo = "SlavaSubotskiy/sy-subtitles"

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
  position: relative; width: 100%; min-height: 60px; padding: 12px 16px;
  background: rgba(0,0,0,0.85); color: #fff; font-size: 40px;
  line-height: 1.4; text-align: center; border-radius: 0 0 4px 4px;
}}
#subtitle-overlay:empty {{ min-height: 20px; }}
#subtitle-overlay:empty::after {{ content: '\\200B'; }}
.controls {{ display: flex; align-items: center; justify-content: center; gap: 12px; padding: 8px; }}
.controls button {{ background: #333; color: #fff; border: 1px solid #555; border-radius: 6px;
  padding: 8px 16px; font-size: 14px; cursor: pointer; touch-action: manipulation; }}
.controls button:active {{ background: #555; }}
#time-display {{ color: #666; font-size: 13px; font-family: monospace; }}
#status {{ text-align: center; padding: 4px; color: #888; font-size: 13px; }}
.markers {{ max-width: 960px; margin: 0 auto; padding: 0 8px; }}
.markers summary {{ color: #888; cursor: pointer; padding: 8px; font-size: 14px; }}
.markers summary:hover {{ color: #fff; }}
.marker-actions {{ display: flex; gap: 8px; padding: 8px 0; }}
.marker-actions button {{ background: #2a4a2a; color: #8f8; border: 1px solid #4a4; border-radius: 6px;
  padding: 6px 14px; font-size: 13px; cursor: pointer; }}
.marker-actions button.issue {{ background: #3a2a4a; color: #c8f; border-color: #84c; }}
.marker-actions button:active {{ opacity: 0.7; }}
.marker-list {{ list-style: none; }}
.marker-item {{ display: flex; align-items: flex-start; gap: 8px; padding: 6px 0;
  border-bottom: 1px solid #333; font-size: 14px; }}
.marker-item .tc {{ color: #6af; cursor: pointer; white-space: nowrap; font-family: monospace; min-width: 70px; }}
.marker-item .tc:hover {{ text-decoration: underline; }}
.marker-item .text {{ color: #ccc; flex: 1; word-break: break-word; }}
.marker-item .del {{ color: #666; cursor: pointer; padding: 0 4px; }}
.marker-item .del:hover {{ color: #f66; }}
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
  <div class="controls">
    <span id="time-display">00:00:00</span>
    <button id="btn-mark" onclick="addMarker()">&#x1F4CC; Mark</button>
  </div>
  <div id="status">Loading subtitles...</div>
</div>

<div class="markers">
  <details id="markers-panel" open>
    <summary>Markers (<span id="marker-count">0</span>)</summary>
    <div class="marker-actions">
      <button onclick="copyMarkers()">Copy all</button>
      <button class="issue" onclick="createIssue()">Create issue</button>
    </div>
    <ul class="marker-list" id="marker-list"></ul>
  </details>
</div>

<script src="https://player.vimeo.com/api/player.js"></script>
<script>
{parser_js}

(function() {{
  var overlay = document.getElementById('subtitle-overlay');
  var timeDisplay = document.getElementById('time-display');
  var status = document.getElementById('status');
  var iframe = document.getElementById('vimeo-player');
  var player = new Vimeo.Player(iframe);
  var subtitles = [];
  var lastText = '';
  var currentSeconds = 0;

  // Expose for marker functions
  window._player = player;
  window._getCurrentTime = function() {{ return currentSeconds; }};
  window._getCurrentSubtitle = function() {{ return lastText; }};

  fetch('{srt_raw_url}')
    .then(function(r) {{ return r.ok ? r.text() : Promise.reject('HTTP ' + r.status); }})
    .then(function(text) {{
      subtitles = parseSRT(text);
      status.textContent = subtitles.length + ' subtitles loaded';
      setTimeout(function() {{ status.style.display = 'none'; }}, 3000);
    }})
    .catch(function(err) {{
      status.textContent = 'Failed to load subtitles: ' + err;
      status.style.color = '#f66';
    }});

  player.on('timeupdate', function(data) {{
    currentSeconds = data.seconds;
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

// --- Markers ---
var STORAGE_KEY = 'markers_' + location.pathname;
var markers = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
renderMarkers();

document.addEventListener('keydown', function(e) {{
  if (e.key === 'm' || e.key === 'M') {{ if (e.target.tagName !== 'INPUT') addMarker(); }}
}});

function fmtTime(sec) {{
  var h = String(Math.floor(sec / 3600)).padStart(2, '0');
  var m = String(Math.floor((sec % 3600) / 60)).padStart(2, '0');
  var s = String(Math.floor(sec % 60)).padStart(2, '0');
  return h + ':' + m + ':' + s;
}}

function addMarker() {{
  var t = window._getCurrentTime();
  var text = window._getCurrentSubtitle() || '(no subtitle)';
  markers.push({{ time: t, tc: fmtTime(t), text: text }});
  saveAndRender();
}}

function removeMarker(i) {{
  markers.splice(i, 1);
  saveAndRender();
}}

function seekTo(sec) {{
  window._player.setCurrentTime(sec);
}}

function saveAndRender() {{
  localStorage.setItem(STORAGE_KEY, JSON.stringify(markers));
  renderMarkers();
}}

function renderMarkers() {{
  var list = document.getElementById('marker-list');
  var count = document.getElementById('marker-count');
  count.textContent = markers.length;
  list.innerHTML = '';
  markers.forEach(function(m, i) {{
    var li = document.createElement('li');
    li.className = 'marker-item';
    li.innerHTML = '<span class="tc" onclick="seekTo(' + m.time + ')">' + m.tc + '</span>' +
      '<span class="text">' + m.text.replace(/</g, '&lt;') + '</span>' +
      '<span class="del" onclick="removeMarker(' + i + ')">&#x2715;</span>';
    list.appendChild(li);
  }});
}}

function markersToText() {{
  var title = document.title;
  var lines = ['# ' + title, ''];
  markers.forEach(function(m) {{
    lines.push('- **' + m.tc + '** ' + m.text);
  }});
  return lines.join('\\n');
}}

function copyMarkers() {{
  navigator.clipboard.writeText(markersToText()).then(function() {{
    var btn = document.querySelector('.marker-actions button');
    var orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(function() {{ btn.textContent = orig; }}, 1500);
  }});
}}

function createIssue() {{
  var title = encodeURIComponent('Subtitle review: {html.escape(video_title)}');
  var body = encodeURIComponent(markersToText());
  window.open('https://github.com/{issue_repo}/issues/new?title=' + title + '&body=' + body);
}}
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


def scan_all_talks(talks_dir: str) -> list:
    """Scan talks directory for all videos with uk.srt."""
    talks = Path(talks_dir)
    entries = []

    for meta_path in sorted(talks.glob("*/meta.yaml")):
        talk_dir = meta_path.parent
        talk_id = talk_dir.name

        with open(meta_path) as f:
            meta = yaml.safe_load(f)

        talk_title = meta.get("title", talk_id)
        date = str(meta.get("date", talk_id[:10]))

        for v in meta.get("videos", []):
            slug = v["slug"]
            srt_path = talk_dir / slug / "final" / "uk.srt"
            if not srt_path.exists():
                continue

            entries.append(
                {
                    "talk_id": talk_id,
                    "talk_title": talk_title,
                    "video_slug": slug,
                    "video_title": v.get("title", slug),
                    "vimeo_url": v.get("vimeo_url", ""),
                    "date": date,
                }
            )

    return entries


def generate_site(
    entries: list, output_dir: str, base_url: str = "", repo: str = DEFAULT_REPO, branch: str = DEFAULT_BRANCH
):
    """Generate full preview site from entries."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    for e in entries:
        embed_url = vimeo_url_to_embed(e["vimeo_url"])
        srt_raw_url = f"{GITHUB_RAW}/{repo}/{branch}/talks/{e['talk_id']}/{e['video_slug']}/final/uk.srt"

        page_html = generate_video_page(e["talk_title"], e["video_title"], embed_url, srt_raw_url, base_url)

        page_dir = out / e["talk_id"] / e["video_slug"]
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(page_html, encoding="utf-8")
        print(f"  {e['talk_id']}/{e['video_slug']}/", file=sys.stderr)

    # Index
    index_html = generate_index_page(entries, base_url)
    (out / "index.html").write_text(index_html, encoding="utf-8")
    print(f"Index: {len(entries)} entries", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description="Generate subtitle preview site")
    p.add_argument("--output-dir", required=True, help="Output directory")
    p.add_argument("--base-url", default="", help="Base URL for links")
    p.add_argument("--repo", default=DEFAULT_REPO, help="GitHub repo (owner/name)")
    p.add_argument("--branch", default=DEFAULT_BRANCH, help="Branch for raw URLs")
    p.add_argument("--talks-dir", default="talks", help="Talks directory to scan")
    args = p.parse_args()

    entries = scan_all_talks(args.talks_dir)
    generate_site(entries, args.output_dir, args.base_url, args.repo, args.branch)


if __name__ == "__main__":
    main()
