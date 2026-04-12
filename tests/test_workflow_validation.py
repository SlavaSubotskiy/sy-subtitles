import pytest

from tools.workflow_validation import (
    InvalidWorkflowInput,
    validate_talk_id,
    validate_video_slug,
    validate_vimeo_url,
)


@pytest.mark.parametrize(
    "value",
    [
        "1988-05-08_Sahasrara-Puja-Fregene",
        "1993-09-19_Ganesha-Puja-Cabella",
        "2001-01-01_a",
        "1970-12-31_slug.with.dots",
    ],
)
def test_talk_id_accepts_valid(value: str) -> None:
    assert validate_talk_id(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "not-a-date",
        "1988-5-8_slug",
        "1988-05-08",
        "1988-05-08_",
        "1988-05-08_slug;rm -rf /",
        "1988-05-08_slug$(curl evil)",
        "1988-05-08_slug with spaces",
        "../escape",
        "1988-05-08_" + "x" * 200,
    ],
)
def test_talk_id_rejects_invalid(value: str) -> None:
    with pytest.raises(InvalidWorkflowInput):
        validate_talk_id(value)


@pytest.mark.parametrize("value", ["morning", "talk_01", "talk-01", "a", "v.1"])
def test_video_slug_accepts(value: str) -> None:
    assert validate_video_slug(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        "a;b",
        "$(whoami)",
        "a b",
        "a/b",
        "x" * 200,
        'slug";curl x;"',
    ],
)
def test_video_slug_rejects(value: str) -> None:
    with pytest.raises(InvalidWorkflowInput):
        validate_video_slug(value)


@pytest.mark.parametrize(
    "value",
    [
        "https://vimeo.com/123456789",
        "https://vimeo.com/123456789/abcdef123",
        "https://player.vimeo.com/video/123456789",
        "https://player.vimeo.com/video/123456789/abcdef0",
        "https://www.vimeo.com/123456789",
    ],
)
def test_vimeo_url_accepts(value: str) -> None:
    assert validate_vimeo_url(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "http://vimeo.com/123",
        "https://youtube.com/watch?v=x",
        "https://vimeo.com/abc",
        "https://vimeo.com/123;curl evil",
        "https://evil.com/#vimeo.com/123",
        "",
    ],
)
def test_vimeo_url_rejects(value: str) -> None:
    with pytest.raises(InvalidWorkflowInput):
        validate_vimeo_url(value)
