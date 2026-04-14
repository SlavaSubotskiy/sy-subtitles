import shutil
import subprocess
from pathlib import Path

import pytest

WORKFLOWS_DIR = Path(__file__).resolve().parents[1] / ".github" / "workflows"

# Filter out pre-existing shellcheck info-level findings; new errors and
# warnings still fail the test.
IGNORE_PATTERNS = [
    r"shellcheck reported issue.*:info:",
]


@pytest.mark.skipif(
    shutil.which("actionlint") is None,
    reason="actionlint not installed (brew install actionlint)",
)
def test_workflows_pass_actionlint() -> None:
    workflows = sorted(WORKFLOWS_DIR.glob("*.yml"))
    assert workflows, f"no workflow files found in {WORKFLOWS_DIR}"

    cmd = ["actionlint"]
    for pattern in IGNORE_PATTERNS:
        cmd.extend(["-ignore", pattern])
    cmd.extend(str(p) for p in workflows)

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        pytest.fail(f"actionlint reported issues:\n{result.stdout}\n{result.stderr}".strip())
