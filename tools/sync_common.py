"""Shared helpers for the sync_srt_to_transcript / sync_transcript_to_srt
pair and the sync_pr driver on top of them.

Keeps git-base lookups and transcript text-splicing primitives in one
place so no single sync tool owns logic that another needs to call.
"""

import subprocess
from pathlib import Path


def load_base_from_git(sha: str, path: str, dest: Path) -> bool:
    """Write the `sha:path` version of a file to `dest`.

    Returns False if the file didn't exist at that SHA (e.g. newly added
    in the PR). Uses `git show` with binary capture so content round-trips
    untouched.
    """
    try:
        data = subprocess.run(
            ["git", "show", f"{sha}:{path}"],
            capture_output=True,
            check=True,
        ).stdout
    except subprocess.CalledProcessError:
        return False
    dest.write_bytes(data)
    return True


def find_in_text(text: str, needle: str, cursor: int) -> int:
    """Return position of `needle` in `text` starting at `cursor`, or -1.

    Thin wrapper around str.find with a consistent signature across the
    sync tools.
    """
    return text.find(needle, cursor)


def delete_from_text(text: str, cursor: int, needle: str) -> dict:
    """Remove the first occurrence of `needle` in `text` at/after `cursor`.

    Trims one adjacent space (if present) to avoid double-spaces. Returns
    a dict with `action` ("removed" or "skipped"), plus `text` and
    `cursor` when removed. Skipped means the text wasn't found — caller
    decides how to handle it.
    """
    pos = find_in_text(text, needle, cursor)
    if pos == -1:
        return {"action": "skipped"}
    end = pos + len(needle)
    if pos > 0 and text[pos - 1] == " ":
        pos -= 1
    elif end < len(text) and text[end] == " ":
        end += 1
    return {"action": "removed", "text": text[:pos] + text[end:], "cursor": pos}
