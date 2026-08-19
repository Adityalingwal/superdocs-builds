"""The export-side citation reader: nothing it recovers may quietly vanish."""
from engine.citations_from_export import (
    cited_sections_from_export,
    missing_citation_failures,
)
from engine.model import Match, Request
from engine.verify_citations import find_citation_failures


def a_request(request_id: str, title: str = "Specialty occupation") -> Request:
    return Request(id=request_id, title=title, text="Provide evidence.")


def a_match(request_id: str, file: str = "01-petition.md") -> Match:
    return Match(
        request_id=request_id, file=file, heading="Duties", excerpt="x", score=1.0
    )


SECTION = """## Response to Request 1 — Specialty occupation

**Petition material relied on:**

- From `01-petition.md`, section "Duties":
  "the beneficiary designs distributed systems"

**Response:**

Prose.
"""


def test_a_multiline_rewrapped_quote_is_checked_in_full():
    rewrapped = SECTION.replace(
        '  "the beneficiary designs distributed systems"',
        '  "the beneficiary designs distributed systems\n  and mentors junior staff"',
    )
    sources = {
        "01-petition.md": "the beneficiary designs distributed systems and mentors staff"
    }
    failures = find_citation_failures(
        cited_sections_from_export(rewrapped), sources
    )
    assert any("Response to Request 1" in failure for failure in failures)


def test_a_reworded_citation_line_is_reported_as_removed():
    reworded = SECTION.replace("- From `01-petition.md`,", "- Based on `01-petition.md`,")
    cited = cited_sections_from_export(reworded)
    failures = missing_citation_failures(
        cited, [a_request("R1")], {"R1": [a_match("R1")]}
    )
    assert any("R1" in failure and "removed" in failure for failure in failures)


def test_fewer_citations_than_checklist_matches_is_reported_with_counts():
    failures = missing_citation_failures(
        cited_sections_from_export(SECTION),
        [a_request("R1")],
        {"R1": [a_match("R1"), a_match("R1", file="02-letter.md")]},
    )
    assert any("1" in failure and "2" in failure for failure in failures)


def test_request_numbers_do_not_match_by_prefix():
    requests = [a_request("R1"), a_request("R10", title="Wage level")]
    matches = {"R1": [a_match("R1")], "R10": [a_match("R10")]}
    failures = missing_citation_failures(
        cited_sections_from_export(SECTION), requests, matches
    )
    assert not any("R1'" in failure for failure in failures)
    assert any("R10" in failure for failure in failures)


def test_a_complete_section_reports_nothing_missing():
    failures = missing_citation_failures(
        cited_sections_from_export(SECTION), [a_request("R1")], {"R1": [a_match("R1")]}
    )
    assert failures == []
