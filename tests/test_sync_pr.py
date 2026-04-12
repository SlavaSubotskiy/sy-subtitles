"""Integration tests for tools.sync_pr driver.

These tests build a real git repo in tmp_path, make a commit representing
the base SHA, then edit files to represent the PR, and invoke sync_pr.run
to exercise the full two-pass flow including per-video effective-old
baseline computation.
"""

import subprocess
from pathlib import Path

import pytest

from tools.sync_pr import _classify, run

HEADER = "Мова промови: англійська | Транскрипт (українська)"

BASE_SRT = """1
00:00:01,000 --> 00:00:03,000
Перше речення першого абзацу.

2
00:00:03,100 --> 00:00:05,000
Друге речення першого абзацу.

3
00:00:05,100 --> 00:00:07,000
Єдине речення другого абзацу.
"""

BASE_TRANSCRIPT = (
    HEADER + "\n\nПерше речення першого абзацу. Друге речення першого абзацу.\n\nЄдине речення другого абзацу.\n"
)


META_TWO_VIDEOS = """videos:
  - slug: Video1
    title: Video One
  - slug: Video2
    title: Video Two
"""


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return result.stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Build a real git repo at tmp_path/repo with a base commit containing
    a two-video talk (Video1 + Video2), identical base transcript and SRTs.
    Returns (repo_path, base_sha). cd's the process into the repo so
    sync_pr's internal `git` calls work."""
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    talk = repo_path / "talks" / "test"
    (talk / "Video1" / "final").mkdir(parents=True)
    (talk / "Video2" / "final").mkdir(parents=True)
    (talk / "meta.yaml").write_text(META_TWO_VIDEOS, encoding="utf-8")
    (talk / "Video1" / "final" / "uk.srt").write_text(BASE_SRT, encoding="utf-8")
    (talk / "Video2" / "final" / "uk.srt").write_text(BASE_SRT, encoding="utf-8")
    (talk / "transcript_uk.txt").write_text(BASE_TRANSCRIPT, encoding="utf-8")

    _git(repo_path, "init", "-q", "-b", "main")
    _git(repo_path, "config", "user.email", "test@example.com")
    _git(repo_path, "config", "user.name", "Test")
    # Explicitly disable GPG signing — the ambient user config may have it
    # enabled (1Password SSH/GPG agent) and tests must not depend on an
    # unlocked signer.
    _git(repo_path, "config", "commit.gpgsign", "false")
    _git(repo_path, "config", "tag.gpgsign", "false")
    _git(repo_path, "add", ".")
    _git(repo_path, "commit", "-q", "-m", "base")
    base_sha = _git(repo_path, "rev-parse", "HEAD").strip()

    monkeypatch.chdir(repo_path)
    return repo_path, base_sha


class TestClassify:
    def test_classifies_transcript_only(self):
        srt, trans = _classify(["talks/2001-01-01_Test/transcript_uk.txt"])
        assert srt == {}
        assert "talks/2001-01-01_Test" in trans

    def test_classifies_srt_only(self):
        srt, trans = _classify(["talks/2001-01-01_Test/Video1/final/uk.srt"])
        assert srt == {"talks/2001-01-01_Test": ["talks/2001-01-01_Test/Video1/final/uk.srt"]}
        assert trans == {}

    def test_classifies_mixed(self):
        srt, trans = _classify(
            [
                "talks/A/transcript_uk.txt",
                "talks/A/V1/final/uk.srt",
                "talks/B/V2/final/uk.srt",
                "README.md",
                "site/index.html",
            ]
        )
        assert trans == {"talks/A": True}
        assert srt == {
            "talks/A": ["talks/A/V1/final/uk.srt"],
            "talks/B": ["talks/B/V2/final/uk.srt"],
        }


class TestSyncPrIntegration:
    def test_transcript_only_pr_syncs_both_videos(self, repo):
        """A PR that only edits transcript_uk.txt should end up with both
        videos' SRTs updated via Step B (Step A does nothing)."""
        repo_path, base_sha = repo
        transcript = repo_path / "talks" / "test" / "transcript_uk.txt"
        transcript.write_text(
            BASE_TRANSCRIPT.replace("Єдине речення другого абзацу.", "Нове речення другого абзацу."),
            encoding="utf-8",
        )
        _git(repo_path, "add", "talks")
        _git(repo_path, "commit", "-q", "-m", "edit transcript")

        exit_code = run(base_sha)
        assert exit_code == 0

        for slug in ("Video1", "Video2"):
            srt = (repo_path / "talks" / "test" / slug / "final" / "uk.srt").read_text(encoding="utf-8")
            assert "Нове речення другого абзацу." in srt
            assert "Єдине речення другого абзацу." not in srt

    def test_srt_only_pr_propagates_to_other_video(self, repo):
        """Editing just Video1's SRT should propagate to Video2's SRT via
        Step A → transcript → Step B, which is the PR #43 original flow."""
        repo_path, base_sha = repo
        v1_srt = repo_path / "talks" / "test" / "Video1" / "final" / "uk.srt"
        v1_srt.write_text(
            BASE_SRT.replace("Перше речення першого абзацу.", "Виправлене перше речення."),
            encoding="utf-8",
        )
        _git(repo_path, "add", "talks")
        _git(repo_path, "commit", "-q", "-m", "edit v1 srt")

        exit_code = run(base_sha)
        assert exit_code == 0

        transcript = (repo_path / "talks" / "test" / "transcript_uk.txt").read_text(encoding="utf-8")
        assert "Виправлене перше речення." in transcript
        assert "Перше речення першого абзацу." not in transcript

        v2_srt = (repo_path / "talks" / "test" / "Video2" / "final" / "uk.srt").read_text(encoding="utf-8")
        assert "Виправлене перше речення." in v2_srt
        assert "Перше речення першого абзацу." not in v2_srt

    def test_mixed_srt_and_transcript_pr_applies_both_edits_everywhere(self, repo):
        """The workflow gap case: a PR edits BOTH Video1's SRT AND
        transcript_uk.txt directly. Expected end state:
        - transcript has both edits
        - Video1 SRT has both edits (its own SRT-level edit plus the
          direct transcript edit propagated by Step B)
        - Video2 SRT inherits both edits via Step B only

        This was the xfail case under the old bash workflow. With the
        per-video effective-old baseline in sync_pr, it passes."""
        repo_path, base_sha = repo
        talk = repo_path / "talks" / "test"
        v1_srt = talk / "Video1" / "final" / "uk.srt"
        v1_srt.write_text(
            BASE_SRT.replace("Перше речення першого абзацу.", "Виправлене перше речення."),
            encoding="utf-8",
        )
        transcript = talk / "transcript_uk.txt"
        transcript.write_text(
            BASE_TRANSCRIPT.replace("Єдине речення другого абзацу.", "Нове речення другого абзацу."),
            encoding="utf-8",
        )
        _git(repo_path, "add", "talks")
        _git(repo_path, "commit", "-q", "-m", "mixed edits")

        exit_code = run(base_sha)
        assert exit_code == 0

        transcript_after = transcript.read_text(encoding="utf-8")
        assert "Виправлене перше речення." in transcript_after
        assert "Нове речення другого абзацу." in transcript_after
        assert "Перше речення першого абзацу." not in transcript_after
        assert "Єдине речення другого абзацу." not in transcript_after

        v1_after = v1_srt.read_text(encoding="utf-8")
        assert "Виправлене перше речення." in v1_after
        assert "Нове речення другого абзацу." in v1_after
        assert "Перше речення першого абзацу." not in v1_after
        assert "Єдине речення другого абзацу." not in v1_after

        v2_after = (talk / "Video2" / "final" / "uk.srt").read_text(encoding="utf-8")
        assert "Виправлене перше речення." in v2_after
        assert "Нове речення другого абзацу." in v2_after
        assert "Перше речення першого абзацу." not in v2_after
        assert "Єдине речення другого абзацу." not in v2_after

    def test_no_changes_returns_zero(self, repo):
        """Nothing changed in the PR — driver should noop and exit 0."""
        repo_path, base_sha = repo
        # Make a noop commit so HEAD != base but no content differs
        (repo_path / "README.md").write_text("unrelated\n", encoding="utf-8")
        _git(repo_path, "add", "README.md")
        _git(repo_path, "commit", "-q", "-m", "unrelated")

        exit_code = run(base_sha)
        assert exit_code == 0

        transcript = (repo_path / "talks" / "test" / "transcript_uk.txt").read_text(encoding="utf-8")
        assert transcript == BASE_TRANSCRIPT
