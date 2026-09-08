"""Guards for the pending-action feedback: its vocabulary and its catalog entry.

Two UX defects are fixed here and both are string-shaped, so they are guarded
as strings:

1. The signed-in write actions ("Create PR" on the add-talk page, Finalize in
   the sync chip, Create issue) run a chain of sequential GitHub calls. The
   trigger now wears a ``.btn--busy`` state that narrates the phase, so the
   wait is neither silent nor clickable twice.
2. ``ghCreatedDialog``'s button said "Open GitHub" under an "PR created"
   title, which reads as an invitation to CREATE a PR. It now says "View on
   GitHub" via its own key — while the copy-and-paste dialogs, whose body text
   literally names the button, keep the original ``modal.open_github``.

The lock and the label vocabulary themselves are unit-tested in
tests/test_pending_action.js; this file guards the wiring in index.html, the
i18n dictionaries and the styleguide catalog.
"""

import re
from pathlib import Path

import pytest

SITE = Path(__file__).parent.parent / "site"
INDEX = (SITE / "index.html").read_text(encoding="utf-8")
COMPONENTS = (SITE / "css" / "components.css").read_text(encoding="utf-8")
STYLEGUIDE = (SITE / "styleguide.html").read_text(encoding="utf-8")

# The busy labels (one per phase of the one-click PR chain, plus the
# single-request actions and the generic fallback) and the disambiguated
# dialog button. pendingStepKey() in site/js/pending_action.js is the producer.
PENDING_KEYS = [
    "pending.branch",
    "pending.commit",
    "pending.pr",
    "pending.issue",
    "pending.working",
]
NEW_KEYS = PENDING_KEYS + ["modal.view_on_github"]


def _i18n_dicts() -> tuple[set[str], set[str]]:
    """The key sets of the uk and en dictionaries in the I18N literal."""
    start = INDEX.index("var I18N =")
    open_brace = INDEX.index("{", start)
    depth = 0
    for end in range(open_brace, len(INDEX)):
        if INDEX[end] == "{":
            depth += 1
        elif INDEX[end] == "}":
            depth -= 1
            if depth == 0:
                break
    blob = INDEX[open_brace : end + 1]
    uk_at, en_at = blob.index("uk: {"), blob.index("en: {")
    keys = lambda seg: set(re.findall(r"'([a-zA-Z0-9_.]+)':", seg))  # noqa: E731
    return keys(blob[uk_at:en_at]), keys(blob[en_at:])


@pytest.mark.parametrize("key", NEW_KEYS)
def test_new_key_is_translated_in_both_languages(key):
    uk, en = _i18n_dicts()
    assert key in uk, f"{key} missing from the Ukrainian dictionary"
    assert key in en, f"{key} missing from the English dictionary"


def test_i18n_dictionaries_stay_in_lockstep():
    """A key added to one dictionary only degrades silently to the raw key."""
    uk, en = _i18n_dicts()
    assert uk == en, f"uk-only: {sorted(uk - en)}; en-only: {sorted(en - uk)}"


def test_created_dialog_button_says_view_not_open():
    """The PR/issue-created dialog must not re-use the paste flows' label."""
    body = INDEX[INDEX.index("function ghCreatedDialog") :][:600]
    assert "modal.view_on_github" in body
    assert "modal.open_github" not in body


def test_paste_dialogs_keep_the_open_github_label():
    """Their body text names the button, so the two must stay in step."""
    assert INDEX.count("t('modal.open_github')") >= 3
    for key in ("modal.copied_body_issue", "modal.copied_body_srt", "modal.copied_body_meta"):
        assert key in INDEX


def test_dead_create_pr_key_is_gone():
    """`btn.create_pr` was translated twice and referenced by nothing."""
    assert "btn.create_pr" not in INDEX


def test_busy_button_state_exists_and_is_catalogued():
    """CLAUDE.md: a new component ships its live styleguide example."""
    assert ".btn--busy" in COMPONENTS
    assert ".btn--busy" in STYLEGUIDE


def test_busy_state_carries_no_palette_of_its_own():
    """EVERY .btn--busy rule, including the ::before that actually paints.

    Matching only the first rule would inspect `opacity`/`cursor` and miss the
    dot — the one declaration that sets a colour.
    """
    rules = re.findall(r"\.btn--busy[^{}]*\{([^}]*)\}", COMPONENTS)
    assert len(rules) >= 3, f"expected the state, dot and reduced-motion rules, got {len(rules)}"
    for body in rules:
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", body), body
    assert any("currentColor" in b for b in rules), "the dot must inherit the variant's ink"


def test_pending_module_is_loaded_by_the_page():
    assert 'src="js/pending_action.js"' in INDEX


def test_finalize_lock_key_is_scoped_to_the_talk():
    """A bare 'sync-finalize' key is global: finalizing talk A would hide the
    Finalize item from talk B's chip until A's chain settled."""
    assert "'sync-finalize'" not in INDEX, "the finalize key must carry the engine's branch"
    assert INDEX.count("finalizeLockKey(") >= 2, "both the dropdown and the action use it"


def test_the_page_owns_no_copy_of_the_runner_logic():
    """CLAUDE.md: the testable logic lives in the module, not inline in the page.

    The paint/restore decisions are pinned by tests/test_pending_action.js; a
    second copy here would be a source the Node suite cannot see.
    """
    assert "function withBusyButton" not in INDEX
    assert "createBusyRunner({" in INDEX


@pytest.mark.parametrize("dep", ["lock: actionLock", "t: t", "announce:"])
def test_runner_is_wired_with_every_dependency_it_needs(dep):
    """Miss `t` and the button shows raw i18n keys; miss `announce` and the
    phase never reaches a screen reader."""
    wiring = INDEX[INDEX.index("createBusyRunner({") :][:500]
    assert dep in wiring


def test_the_live_region_the_runner_announces_into_exists():
    """aria-busy on a button announces nothing on its own."""
    assert 'id="sr-action-status"' in INDEX
    region = INDEX[INDEX.index('id="sr-action-status"') - 200 :][:400]
    assert 'aria-live="polite"' in region and 'class="sr-only"' in region
