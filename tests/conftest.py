"""Shared test fixtures."""

import json
from pathlib import Path

import pytest

from tools.config import OptimizeConfig
from tools.srt_utils import parse_srt

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_srt_path():
    return FIXTURES / "sample.srt"


@pytest.fixture
def sample_whisper_path():
    return FIXTURES / "sample_whisper.json"


@pytest.fixture
def sample_transcript_en_path():
    return FIXTURES / "sample_transcript_en.txt"


@pytest.fixture
def sample_transcript_uk_path():
    return FIXTURES / "sample_transcript_uk.txt"


@pytest.fixture
def sample_blocks(sample_srt_path):
    return parse_srt(sample_srt_path)


@pytest.fixture
def sample_whisper_segments(sample_whisper_path):
    with open(sample_whisper_path) as f:
        data = json.load(f)
    return data["segments"]


@pytest.fixture
def default_config():
    return OptimizeConfig()


@pytest.fixture
def tmp_srt(tmp_path):
    return tmp_path / "output.srt"


@pytest.fixture
def tmp_json(tmp_path):
    return tmp_path / "output.json"
