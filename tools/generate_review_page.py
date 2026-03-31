"""Generate translation review pages for GitHub Pages.

Side-by-side EN/UK transcript view with inline editing and issue creation.

Usage:
    python -m tools.generate_review_page --output-dir /tmp/site --talks-dir talks
"""

import argparse
import html
import sys
from pathlib import Path

import yaml

GITHUB_RAW = "https://raw.githubusercontent.com"
DEFAULT_REPO = "SlavaSubotskiy/sy-subtitles"
DEFAULT_BRANCH = "main"


def generate_review_page(
    talk_title: str,
    talk_id: str,
    en_raw_url: str,
    uk_raw_url: str,
    base_url: str = "",
    repo: str = DEFAULT_REPO,
) -> str:
    """Generate side-by-side translation review page."""
    edit_url = f"https://github.com/{repo}/edit/main/talks/{talk_id}/transcript_uk.txt"
    esc_title = html.escape(talk_title)
    esc_talk_id = html.escape(talk_id)

    return f"""<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Review: {esc_title}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: #1a1a1a; color: #fff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
.header {{ padding: 12px 20px; background: #111; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }}
.header h1 {{ font-size: 16px; font-weight: normal; color: #aaa; }}
.header a {{ color: #6af; text-decoration: none; }}
.header-actions {{ display: flex; gap: 8px; }}
.header-actions button {{ background: #333; color: #fff; border: 1px solid #555; border-radius: 6px;
  padding: 6px 14px; font-size: 13px; cursor: pointer; }}
.header-actions button.primary {{ background: #2a4a2a; border-color: #4a4; color: #8f8; }}
.header-actions button.issue {{ background: #3a2a4a; border-color: #84c; color: #c8f; }}
.header-actions button:active {{ opacity: 0.7; }}
#status {{ text-align: center; padding: 12px; color: #888; }}
.grid {{ display: grid; grid-template-columns: 1fr 1fr; max-width: 1400px; margin: 0 auto; }}
.col-header {{ padding: 10px 16px; background: #222; font-size: 13px; color: #888; text-transform: uppercase;
  position: sticky; top: 0; z-index: 1; }}
.row {{ display: contents; }}
.cell {{ padding: 10px 16px; border-bottom: 1px solid #2a2a2a; font-size: 15px; line-height: 1.5;
  min-height: 40px; transition: background 0.15s; }}
.cell.en {{ color: #aaa; }}
.cell.uk {{ color: #eee; cursor: text; }}
.cell.uk:hover {{ background: #222; }}
.cell.uk:focus {{ background: #1a2a1a; outline: 1px solid #4a4; }}
.cell.uk.edited {{ background: #2a2a1a; }}
.cell.uk.marked {{ border-left: 3px solid #84c; }}
.cell-actions {{ display: flex; gap: 4px; margin-top: 6px; }}
.cell-actions button {{ background: none; border: 1px solid #444; border-radius: 4px; color: #888;
  font-size: 12px; padding: 2px 8px; cursor: pointer; }}
.cell-actions button:hover {{ color: #fff; border-color: #888; }}
.cell-actions button.active {{ color: #c8f; border-color: #84c; }}
.comment-input {{ width: 100%; background: #2a2a2a; color: #eee; border: 1px solid #444;
  border-radius: 4px; padding: 4px 8px; font-size: 13px; margin-top: 4px; display: none; }}
.comment-input.visible {{ display: block; }}
.comment-input:focus {{ border-color: #6af; outline: none; }}
.counter {{ position: fixed; bottom: 16px; right: 16px; background: #222; border: 1px solid #444;
  border-radius: 8px; padding: 8px 14px; font-size: 13px; color: #888; }}
.counter span {{ color: #fff; }}
@media (max-width: 768px) {{
  .grid {{ grid-template-columns: 1fr; }}
  .col-header.en, .cell.en {{ display: none; }}
}}
</style>
</head>
<body>
<div class="header">
  <h1><a href="{base_url}/">&larr; Index</a> &middot; {esc_title}</h1>
  <div class="header-actions">
    <button class="issue" onclick="createIssue()">Create Issue</button>
    <button class="primary" onclick="openEditor()">Open in GitHub Editor</button>
  </div>
</div>
<div id="status">Loading transcripts...</div>
<div class="grid" id="grid">
  <div class="col-header en">English (original)</div>
  <div class="col-header uk">Ukrainian (translation)</div>
</div>
<div class="counter" id="counter" style="display:none">
  <span id="mark-count">0</span> marks &middot; <span id="edit-count">0</span> edits
</div>

<script>
var REPO = '{repo}';
var TALK_ID = '{esc_talk_id}';
var EN_URL = '{en_raw_url}';
var UK_URL = '{uk_raw_url}';
var EDIT_URL = '{edit_url}';
var STORAGE_KEY = 'review_' + TALK_ID;

var state = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{{"marks":{{}},"edits":{{}}}}');
var enParas = [];
var ukParas = [];

function parseTranscript(text) {{
  var lines = text.split('\\n');
  var bodyStart = 0;
  for (var i = 0; i < Math.min(lines.length, 10); i++) {{
    if (/^(Talk Language:|Language:|Мова промови:|Мова:)/i.test(lines[i].trim())) {{
      bodyStart = i + 1;
      break;
    }}
  }}
  var body = lines.slice(bodyStart).join('\\n');
  // Detect format: if double newlines exist, split on them; otherwise single newlines
  if (/\\n\\s*\\n/.test(body)) {{
    return body.split(/\\n\\s*\\n/).map(function(p) {{ return p.trim(); }}).filter(Boolean);
  }}
  return body.split('\\n').map(function(p) {{ return p.trim(); }}).filter(Boolean);
}}

Promise.all([
  fetch(EN_URL).then(function(r) {{ return r.ok ? r.text() : Promise.reject('EN: ' + r.status); }}),
  fetch(UK_URL).then(function(r) {{ return r.ok ? r.text() : Promise.reject('UK: ' + r.status); }})
]).then(function(texts) {{
  enParas = parseTranscript(texts[0]);
  ukParas = parseTranscript(texts[1]);
  render();
  document.getElementById('status').style.display = 'none';
}}).catch(function(err) {{
  document.getElementById('status').textContent = 'Error: ' + err;
  document.getElementById('status').style.color = '#f66';
}});

function render() {{
  var grid = document.getElementById('grid');
  var n = Math.max(enParas.length, ukParas.length);
  for (var i = 0; i < n; i++) {{
    var en = enParas[i] || '';
    var uk = ukParas[i] || '';
    var edited = state.edits[i] !== undefined;
    var marked = state.marks[i] !== undefined;
    var displayUk = edited ? state.edits[i] : uk;

    var row = document.createElement('div');
    row.className = 'row';
    row.innerHTML =
      '<div class="cell en" data-idx="' + i + '">' +
        '<div class="para-num" style="color:#555;font-size:11px;margin-bottom:2px">P' + (i + 1) + '</div>' +
        escHtml(en) +
      '</div>' +
      '<div class="cell uk' + (edited ? ' edited' : '') + (marked ? ' marked' : '') + '" ' +
        'contenteditable="true" data-idx="' + i + '" ' +
        'oninput="onEdit(' + i + ', this)" onfocus="onFocus(' + i + ')">' +
        '<div class="para-num" style="color:#555;font-size:11px;margin-bottom:2px">P' + (i + 1) + '</div>' +
        escHtml(displayUk) +
      '</div>';
    grid.appendChild(row);
  }}
  updateCounter();
}}

function escHtml(s) {{
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}}

function onEdit(idx, el) {{
  var text = el.innerText.replace(/^P\\d+\\n/, '').trim();
  var orig = ukParas[idx] || '';
  if (text === orig) {{
    delete state.edits[idx];
    el.classList.remove('edited');
  }} else {{
    state.edits[idx] = text;
    el.classList.add('edited');
  }}
  save();
}}

function onFocus(idx) {{
  // Show mark button on focus — handled via CSS hover
}}

function toggleMark(idx) {{
  if (state.marks[idx] !== undefined) {{
    delete state.marks[idx];
  }} else {{
    state.marks[idx] = '';
  }}
  save();
  var cell = document.querySelector('.cell.uk[data-idx="' + idx + '"]');
  if (cell) cell.classList.toggle('marked');
}}

function updateComment(idx, val) {{
  state.marks[idx] = val;
  save();
}}

function save() {{
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  updateCounter();
}}

function updateCounter() {{
  var mc = Object.keys(state.marks).length;
  var ec = Object.keys(state.edits).length;
  document.getElementById('mark-count').textContent = mc;
  document.getElementById('edit-count').textContent = ec;
  document.getElementById('counter').style.display = (mc + ec > 0) ? 'block' : 'none';
}}

document.addEventListener('keydown', function(e) {{
  if ((e.ctrlKey || e.metaKey) && e.key === 'm') {{
    e.preventDefault();
    var el = document.activeElement;
    if (el && el.classList.contains('uk')) {{
      var idx = parseInt(el.getAttribute('data-idx'));
      toggleMark(idx);
    }}
  }}
}});

function issueBody() {{
  var gh = 'https://github.com/' + REPO;
  var lines = [
    '## Translation review: {esc_title}',
    '',
    '| | |',
    '|---|---|',
    '| Transcript | [`talks/' + TALK_ID + '/transcript_uk.txt`](' + gh + '/blob/main/talks/' + TALK_ID + '/transcript_uk.txt) |',
    '| Review page | ' + location.href + ' |',
    ''
  ];

  var markIdxs = Object.keys(state.marks).map(Number).sort(function(a, b) {{ return a - b; }});
  if (markIdxs.length) {{
    lines.push('### Marked paragraphs', '');
    lines.push('| P# | English | Ukrainian | Comment |');
    lines.push('|----|---------|-----------|---------|');
    markIdxs.forEach(function(idx) {{
      var en = enParas[idx] || '';
      var uk = state.edits[idx] || ukParas[idx] || '';
      var comment = state.marks[idx] || '';
      lines.push('| P' + (idx + 1) + ' | ' + en + ' | ' + uk + ' | ' + comment + ' |');
    }});
  }}

  var editIdxs = Object.keys(state.edits).map(Number).sort(function(a, b) {{ return a - b; }});
  if (editIdxs.length) {{
    lines.push('', '### Suggested edits', '');
    editIdxs.forEach(function(idx) {{
      var orig = ukParas[idx] || '';
      var edited = state.edits[idx];
      lines.push('<details><summary><b>P' + (idx + 1) + '</b></summary>');
      lines.push('');
      lines.push('**Before:**');
      lines.push('> ' + orig.split('\\n').join('\\n> '));
      lines.push('');
      lines.push('**After:**');
      lines.push('> ' + edited.split('\\n').join('\\n> '));
      lines.push('');
      lines.push('</details>');
      lines.push('');
    }});
  }}

  return lines.join('\\n');
}}

function createIssue() {{
  var title = encodeURIComponent('Translation review: {esc_title}');
  var body = encodeURIComponent(issueBody());
  window.open('https://github.com/' + REPO + '/issues/new?title=' + title + '&body=' + body + '&labels=review');
}}

function buildEditedTranscript() {{
  // Reconstruct full transcript with edits applied
  var lines = [];
  for (var i = 0; i < ukParas.length; i++) {{
    if (state.edits[i] !== undefined) {{
      lines.push(state.edits[i]);
    }} else {{
      lines.push(ukParas[i]);
    }}
  }}
  return lines.join('\\n');
}}

function openEditor() {{
  var hasEdits = Object.keys(state.edits).length > 0;
  if (hasEdits) {{
    navigator.clipboard.writeText(buildEditedTranscript()).then(function() {{
      alert('Edited transcript copied to clipboard.\\nGitHub editor will open — select all (Ctrl+A) and paste (Ctrl+V).');
      window.open(EDIT_URL);
    }});
  }} else {{
    window.open(EDIT_URL);
  }}
}}
</script>
</body>
</html>"""


def scan_talks_with_transcripts(talks_dir: str) -> list:
    """Scan talks directory for talks with both EN and UK transcripts."""
    talks = Path(talks_dir)
    entries = []

    for meta_path in sorted(talks.glob("*/meta.yaml")):
        talk_dir = meta_path.parent
        talk_id = talk_dir.name

        en_path = talk_dir / "transcript_en.txt"
        uk_path = talk_dir / "transcript_uk.txt"
        if not en_path.exists() or not uk_path.exists():
            continue

        with open(meta_path) as f:
            meta = yaml.safe_load(f)

        entries.append(
            {
                "talk_id": talk_id,
                "talk_title": meta.get("title", talk_id),
                "date": str(meta.get("date", talk_id[:10])),
            }
        )

    return entries


def generate_review_site(
    entries: list,
    output_dir: str,
    base_url: str = "",
    repo: str = DEFAULT_REPO,
    branch: str = DEFAULT_BRANCH,
):
    """Generate review pages for all talks."""
    out = Path(output_dir)

    for e in entries:
        en_url = f"{GITHUB_RAW}/{repo}/{branch}/talks/{e['talk_id']}/transcript_en.txt"
        uk_url = f"{GITHUB_RAW}/{repo}/{branch}/talks/{e['talk_id']}/transcript_uk.txt"

        page_html = generate_review_page(e["talk_title"], e["talk_id"], en_url, uk_url, base_url, repo)

        page_dir = out / e["talk_id"] / "review"
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(page_html, encoding="utf-8")
        print(f"  {e['talk_id']}/review/", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description="Generate translation review pages")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--base-url", default="")
    p.add_argument("--repo", default=DEFAULT_REPO)
    p.add_argument("--branch", default=DEFAULT_BRANCH)
    p.add_argument("--talks-dir", default="talks")
    args = p.parse_args()

    entries = scan_talks_with_transcripts(args.talks_dir)
    generate_review_site(entries, args.output_dir, args.base_url, args.repo, args.branch)
    print(f"Review pages: {len(entries)}", file=sys.stderr)


if __name__ == "__main__":
    main()
