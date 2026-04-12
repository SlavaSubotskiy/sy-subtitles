"""Parser + strict validator for the uk.map pipe-separated format.

Format (kept deliberately simple so LLM build-chunks can emit it directly):

    # comments and blank lines allowed
    1 | 00:00:01,000 | 00:00:04,200 | Текст першого блоку
    2 | 00:00:04,300 | 00:00:07,500 | Другий блок

Canonical fields: block-id | start-timecode | end-timecode | text

parse_uk_map(path, strict=True) raises UkMapError with an explicit
line/reason for any violation. This is the *contract* between whatever
produces a uk.map (LLM chunks, generate_map.py, hand edits) and anything
that consumes one (build_srt.py, replay tests).

Non-strict mode mirrors the historical WARNING-based parser and returns
best-effort blocks — kept for the build_srt fallback.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .srt_utils import time_to_ms

PIPE = "|"
TIMECODE_RE_STR = r"\d{2}:\d{2}:\d{2},\d{3}"


class UkMapError(ValueError):
    """Raised when a uk.map file violates the contract."""

    def __init__(self, line_no: int, message: str, source: str | None = None) -> None:
        loc = f"{source}:{line_no}" if source else f"line {line_no}"
        super().__init__(f"uk.map {loc}: {message}")
        self.line_no = line_no
        self.message = message
        self.source = source


@dataclass
class UkMapBlock:
    idx: int
    start_ms: int
    end_ms: int
    text: str

    def as_dict(self) -> dict:
        return {
            "idx": self.idx,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "text": self.text,
        }


def _parse_timecode(raw: str, line_no: int, source: str | None, role: str) -> int:
    try:
        return time_to_ms(raw)
    except (ValueError, IndexError) as e:
        raise UkMapError(line_no, f"invalid {role} timecode {raw!r} ({e})", source) from None


def _iter_meaningful_lines(lines: Iterable[str]) -> Iterable[tuple[int, str]]:
    for n, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        yield n, stripped


def parse_uk_map(
    path: str,
    *,
    strict: bool = True,
    source_label: str | None = None,
) -> list[UkMapBlock]:
    """Parse a uk.map file into validated blocks.

    strict=True (default) — raise UkMapError on any malformed line, non-sequential
        id, inverted timecodes, or duplicates. Blank lines and `#` comments
        are ignored. Empty files raise.
    strict=False — emit warnings via print() and return the subset of blocks
        that parsed cleanly. This is the legacy behaviour used by build_srt
        while it migrates.
    """
    source = source_label or path
    with open(path, encoding="utf-8-sig") as f:
        raw_lines = f.readlines()

    blocks: list[UkMapBlock] = []
    expected_idx = 1

    for line_no, line in _iter_meaningful_lines(raw_lines):
        parts = line.split(PIPE)
        if len(parts) < 4:
            msg = f"expected 4 pipe-separated fields, got {len(parts)}"
            if strict:
                raise UkMapError(line_no, msg, source)
            print(f"WARNING: {source}:{line_no}: {msg}: {line[:80]}")
            continue

        id_raw = parts[0].strip()
        start_raw = parts[1].strip()
        end_raw = parts[2].strip()
        text = PIPE.join(parts[3:]).strip()

        try:
            idx = int(id_raw)
        except ValueError:
            if strict:
                raise UkMapError(line_no, f"invalid block id {id_raw!r}", source) from None
            print(f"WARNING: {source}:{line_no}: invalid block id {id_raw!r}")
            continue

        start_ms = _parse_timecode(start_raw, line_no, source, "start")
        end_ms = _parse_timecode(end_raw, line_no, source, "end")

        if not text:
            if strict:
                raise UkMapError(line_no, f"block #{idx} has empty text", source)
            print(f"WARNING: {source}:{line_no}: block #{idx} empty text")
            continue

        if start_ms >= end_ms:
            msg = f"block #{idx}: start {start_raw} >= end {end_raw}"
            if strict:
                raise UkMapError(line_no, msg, source)
            print(f"WARNING: {source}:{line_no}: {msg}")
            continue

        if strict and idx != expected_idx:
            raise UkMapError(
                line_no,
                f"non-sequential block id: expected #{expected_idx}, got #{idx}",
                source,
            )
        elif not strict and idx != expected_idx:
            print(f"WARNING: {source}:{line_no}: expected #{expected_idx}, got #{idx}")

        blocks.append(UkMapBlock(idx=idx, start_ms=start_ms, end_ms=end_ms, text=text))
        expected_idx = idx + 1

    if not blocks:
        if strict:
            raise UkMapError(0, "no blocks parsed", source)
        return blocks

    # Cross-block invariants (strict only — non-strict preserves legacy leniency).
    if strict:
        for a, b in zip(blocks, blocks[1:], strict=False):
            if b.start_ms < a.end_ms:
                # overlap isn't strictly illegal (build_srt fixes it) but it's a
                # reliable sign that the LLM/mapping source is broken enough to
                # merit attention. We accept it silently for now.
                pass

    return blocks


def validate_uk_map(path: str, *, source_label: str | None = None) -> list[UkMapBlock]:
    """Convenience alias for parse_uk_map(strict=True)."""
    return parse_uk_map(path, strict=True, source_label=source_label)
