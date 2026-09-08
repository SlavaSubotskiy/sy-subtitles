"""The two files this project treats as its own contract must know about the burn feature.

CLAUDE.md and ARCHITECTURE.md are what a fresh session reads before touching
anything, so a tool that is missing from both is a tool that will be rewritten
rather than reused. The burn feature added two modules and a top-level
directory; this pins that all three are described, and that the usage block
carries the one flag the workflow actually depends on.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(name):
    with open(ROOT / name, encoding="utf-8") as f:
        return f.read()


def test_claude_md_lists_the_render_gate_cli():
    """render_gate must stay in CLAUDE.md's tool index.

    The assertion follows the index's current shape (a bare backticked name in
    the fenced list) rather than the old `tools.render_gate` usage block, which
    no longer exists: CLAUDE.md stopped carrying CLI signatures because they
    duplicated `--help` and drifted from it. The general guard for this now
    lives in tests/test_claude_md_lockstep.py and covers every CLI tool; this
    one keeps render_gate specifically pinned, since the burn feature is what
    it was written for.
    """
    text = _read("CLAUDE.md")
    assert "`render_gate`" in text, (
        "render_gate is the load-bearing piece of the progress mechanism and belongs in CLAUDE.md's tool index"
    )
    listing = text[text.index("**Run by workflows") :]
    assert "`render_gate`" in listing, "it is run by a workflow, not by hand"


def test_architecture_documents_the_progress_file_mechanism():
    """The gate mechanism hangs off the ffmpeg progress file — say so somewhere.

    This used to demand that CLAUDE.md's `burn_subtitles` usage block spell the
    `--progress-file` flag. That block is gone (flags belong to `--help`, which
    cannot go stale), so the requirement moved to the document that actually
    owns the coupling: ARCHITECTURE.md explains that the job writes a progress
    file and that render_gate blocks on it. The point was never the flag's
    spelling — it was that a reader learns the workflow cannot drive the tool
    without it.
    """
    section = _read("ARCHITECTURE.md")
    section = section[section.index("### burn-subtitles.yml") :]
    section = section[: section.index("\n## ")]
    assert "progress" in section.lower(), (
        "the burn section must explain the progress-file channel the gate steps block on"
    )
    assert "render_gate" in section


def test_architecture_lists_both_new_tools():
    tree = _read("ARCHITECTURE.md")
    tree = tree[tree.index("├── tools/") : tree.index("├── site/")]
    for module in ("burn_subtitles.py", "render_gate.py"):
        assert module in tree, f"the per-file tools/ tree omits {module}"


def test_architecture_shows_the_vendored_font_directory():
    # The whole line-break-fidelity argument rests on the vendored face, so a
    # repo tree without assets/ hides the thing the burn output depends on.
    tree = _read("ARCHITECTURE.md")
    assert "├── assets/" in tree or "└── assets/" in tree


def test_architecture_explains_why_the_gate_steps_exist():
    """A reader must learn WHY there are nineteen gate steps without opening the YAML."""
    text = _read("ARCHITECTURE.md")
    section = text[text.index("### burn-subtitles.yml") :]
    section = section[: section.index("\n## ")]
    assert "render_gate" in section
    assert "step" in section.lower()
