"""Lockstep guard: CLAUDE.md may not drift from the repo it describes.

CLAUDE.md is loaded into every session automatically, so a stale line there is
worse than a stale line anywhere else — it is read as instruction, not as
documentation, and nobody goes looking for a source to check it against.

The file therefore keeps only what the code does NOT own (rules, decisions, the
reason a mechanism is shaped the way it is) plus a bare index of what exists, so
a session knows what to reach for. Signatures, flags and measurements were
removed deliberately: those live in `--help` and in the code, and duplicating
them here just creates a second copy that rots. This guard pins the little that
is still enumerated.

Sibling guards using the same idiom: tests/test_sw_precache.js (SW shell list),
tests/test_styleguide_palette_coverage.py (palette catalog),
tests/test_ruff_pin_lockstep.py (pinned versions).
"""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
CLAUDE_MD = ROOT / "CLAUDE.md"

# Workflows a contributor never invokes directly and that carry no instruction
# value here: they are triggered by other workflows or by a bot. Listing them
# would be noise, so their absence is declared rather than caught.
WORKFLOW_EXEMPT: set[str] = set()

# The workflow index is fenced by markers so this guard reads the LIST and not
# the whole file — a workflow mentioned in passing inside some tool's comment is
# not an index entry, and treating it as one let a gap through once already.
# Markers also survive the prose around them being rewritten.
WORKFLOW_LIST_START = "<!-- workflow-index:start -->"
WORKFLOW_LIST_END = "<!-- workflow-index:end -->"

# Same fencing for the tool index — the entries there name tools bare
# (`download`), so without a fence this guard cannot tell a tool name from any
# other backticked word in the prose.
TOOL_LIST_START = "<!-- tool-index:start -->"
TOOL_LIST_END = "<!-- tool-index:end -->"

# Modules with a CLI that a contributor is not expected to reach for directly.
TOOL_INDEX_EXEMPT = {
    "workflow_validation_cli",  # a guard step inside subtitle-pipeline.yml
}


def claude_md() -> str:
    return CLAUDE_MD.read_text(encoding="utf-8")


def workflow_index() -> str:
    text = claude_md()
    start = text.find(WORKFLOW_LIST_START)
    end = text.find(WORKFLOW_LIST_END)
    assert start != -1 and end > start, (
        f"CLAUDE.md must fence its workflow index with {WORKFLOW_LIST_START} … "
        f"{WORKFLOW_LIST_END} so this guard can tell the index from prose"
    )
    return text[start:end]


def workflows_on_disk() -> set[str]:
    return {p.name for p in (ROOT / ".github" / "workflows").glob("*.yml")}


def test_every_workflow_on_disk_is_in_the_index():
    """A workflow nobody indexed is a workflow nobody knows to look at."""
    missing = sorted(w for w in workflows_on_disk() - WORKFLOW_EXEMPT if w not in workflow_index())
    assert not missing, (
        "workflows exist but CLAUDE.md's index omits them: "
        + ", ".join(missing)
        + " — add them to the fenced index, or to WORKFLOW_EXEMPT with a reason "
        "if a contributor genuinely never touches them."
    )


def test_the_index_names_no_workflow_that_is_gone():
    """The other direction: a removed workflow must not linger as an instruction."""
    named = set(re.findall(r"`([a-z0-9._-]+\.yml)`", workflow_index()))

    stale = sorted(named - workflows_on_disk())
    assert not stale, "CLAUDE.md's workflow index names workflows that no longer exist: " + ", ".join(stale)


def tool_index() -> str:
    text = claude_md()
    start = text.find(TOOL_LIST_START)
    end = text.find(TOOL_LIST_END)
    assert start != -1 and end > start, (
        f"CLAUDE.md must fence its tool index with {TOOL_LIST_START} … "
        f"{TOOL_LIST_END} so this guard knows which backticked words are tools"
    )
    return text[start:end]


def test_every_tool_named_in_claude_md_exists():
    """`python -m tools.X` anywhere in the docs must resolve to a module."""
    named = set(re.findall(r"\btools\.([a-z_][a-z0-9_]*)", claude_md()))
    missing = sorted(m for m in named if not (ROOT / "tools" / f"{m}.py").exists())

    assert not missing, "CLAUDE.md points at tools that do not exist: " + ", ".join(f"tools/{m}.py" for m in missing)


def test_every_tool_in_the_index_exists():
    """The index names tools bare (`download`), not dotted — check those too.

    Without this the index could rename or invent a tool and nothing would
    notice: the dotted-form guard above simply would not see it.
    """
    named = set(re.findall(r"^- `([a-z_][a-z0-9_]*)`", tool_index(), re.MULTILINE))
    named |= set(re.findall(r"`([a-z_][a-z0-9_]*)`", _workflow_run_line(tool_index())))
    assert named, "the tool index parsed as empty — has its format changed?"

    missing = sorted(m for m in named if not (ROOT / "tools" / f"{m}.py").exists())
    assert not missing, "CLAUDE.md's tool index names tools that do not exist: " + ", ".join(
        f"tools/{m}.py" for m in missing
    )


def _workflow_run_line(index_text: str) -> str:
    """The 'run by workflows' group lists several tools inline on one line."""
    m = re.search(r"\*\*Run by workflows[^\n]*\n([^\n]*)", index_text)
    return m.group(1) if m else ""


def test_every_tool_with_a_cli_is_in_the_index():
    """A tool nobody indexed is a tool nobody knows to reach for.

    That is not hypothetical: `serve_auth_local` existed, was discoverable by
    `ls tools/`, and still went unused while the SPA was reviewed through a bare
    http.server that cannot reach anything behind sign-in.

    Only modules that actually expose a CLI are required — the rest are
    libraries, and listing them would be noise.
    """
    index = tool_index()
    missing = []
    for path in sorted((ROOT / "tools").glob("*.py")):
        name = path.stem
        if name.startswith("_") or name in TOOL_INDEX_EXEMPT:
            continue
        source = path.read_text(encoding="utf-8")
        has_cli = "__main__" in source and "argparse" in source
        if has_cli and f"`{name}`" not in index:
            missing.append(name)

    assert not missing, (
        "these tools expose a CLI but CLAUDE.md's index omits them: "
        + ", ".join(missing)
        + " — add a line saying what each is FOR (not its flags), or list it in "
        "TOOL_INDEX_EXEMPT if it is genuinely internal."
    )


def test_every_repo_path_named_in_claude_md_exists():
    """Backticked repo paths must resolve — a dead path sends a session hunting."""
    named = set(
        re.findall(
            r"`((?:tools|tests|site|glossary|docs|templates|assets|workers)/[A-Za-z0-9_./-]+)`",
            claude_md(),
        )
    )
    missing = sorted(p for p in named if not (ROOT / p).exists())

    assert not missing, "CLAUDE.md points at paths that do not exist: " + ", ".join(missing)


def test_claude_md_carries_no_cli_flag_documentation():
    """The anti-rot rule itself, enforced.

    Flags belong to `--help`, which cannot go out of date because argparse
    generates it from the parser the command actually runs. Ninety-four of them
    were copied into CLAUDE.md once; keeping that copy in sync by hand is work
    nobody does, so the copy is banned rather than maintained.

    A flag may still be NAMED in prose when the point is the decision behind it
    (a default that is surprising, a flag that must not be used) — what this
    forbids is the option-list shape: `[--flag VALUE]`.
    """
    offenders = [
        f"{i}: {line.strip()}"
        for i, line in enumerate(claude_md().splitlines(), 1)
        if re.search(r"\[--[a-z][a-z0-9-]*(?:\s+[A-Z|]|\])", line)
    ]
    assert not offenders, (
        "CLAUDE.md is documenting CLI option lists again — that duplicates "
        "`--help` and rots. Say what the tool is FOR; let --help say how:\n  " + "\n  ".join(offenders)
    )
