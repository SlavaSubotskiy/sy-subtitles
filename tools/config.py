"""Optimization configuration."""

from dataclasses import dataclass


@dataclass
class OptimizeConfig:
    target_cps: float = 15.0
    hard_max_cps: float = 20.0
    max_cpl: int = 84
    max_lines: int = 1
    max_chars_block: int = 84
    min_duration_ms: int = 1200
    max_duration_ms: int = 21000
    min_gap_ms: int = 80
    fps: int = 24
    single_line: bool = True
    sparse_cps_threshold: float = 2.0
    skip_duration_split: bool = False
    skip_cps_split: bool = False
