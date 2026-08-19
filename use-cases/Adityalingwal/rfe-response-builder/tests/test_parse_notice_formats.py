from pathlib import Path

import pytest

from engine.requests_from_notice import parse_notice

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def style_b():
    return (FIXTURES / "notice-style-b-numbered-list.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def style_c():
    return (FIXTURES / "notice-style-c-request-labels.md").read_text(encoding="utf-8")


def test_a_plain_numbered_list_notice_yields_the_same_five_requests(style_b):
    requests = parse_notice(style_b)
    assert [r.id for r in requests] == ["R1", "R2", "R3", "R4", "R5"]
    assert "nonimmigrant" in requests[4].text


def test_a_request_labelled_notice_yields_the_same_five_requests(style_c):
    requests = parse_notice(style_c)
    assert [r.id for r in requests] == ["R1", "R2", "R3", "R4", "R5"]
    assert "specialty occupation" in requests[1].text


def test_no_request_is_invented_in_any_supported_style(style_b, style_c):
    for notice in (style_b, style_c):
        for request in parse_notice(notice):
            assert request.text in notice


def test_every_style_gives_each_request_a_usable_title(style_b, style_c):
    for notice in (style_b, style_c):
        for request in parse_notice(notice):
            assert request.title.strip()
