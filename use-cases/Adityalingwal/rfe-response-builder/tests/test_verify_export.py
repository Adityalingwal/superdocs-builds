import re

import pytest

from engine.coverage_checklist import build_checklist
from engine.model import ChecklistRow, Coverage
from engine.requests_from_notice import parse_notice
from engine.response_skeleton import build_skeleton
from engine.retrieve_petition_material import retrieve
from engine.verify_export import response_slices, verify_export

PARTIAL_GAP = (
    "**Evidence gap:** the petition only touches this point in general "
    "terms. New evidence is needed — needs attorney confirmation."
)
NOT_PROVIDED_GAP = (
    "**Evidence gap:** the petition contains no material addressing this "
    "request. The required evidence is not provided — needs attorney "
    "confirmation before this section can be completed."
)


@pytest.fixture(scope="module")
def corpus(notice_text, sections, retrieval_config):
    requests = parse_notice(notice_text)
    matches = retrieve(requests, sections, retrieval_config)
    checklist = build_checklist(requests, matches, retrieval_config)
    return requests, checklist


def drafted(skeleton: str) -> str:
    return re.sub(
        r"\[DRAFT RESPONSE FOR R\d+ — TO BE WRITTEN\]",
        "The petition provides the requested material.",
        skeleton,
    )


def test_a_fully_drafted_export_passes(corpus):
    requests, checklist = corpus
    export = drafted(build_skeleton(requests, checklist))
    assert verify_export(export, requests, checklist) == []


def test_a_surviving_placeholder_fails_the_run(corpus):
    requests, checklist = corpus
    export = build_skeleton(requests, checklist)
    failures = verify_export(export, requests, checklist)
    assert any("placeholder survived" in f for f in failures)


def test_a_dropped_response_section_is_named(corpus):
    requests, checklist = corpus
    export = drafted(build_skeleton(requests, checklist))
    export = export.replace("## Response to Request 5", "## Removed")
    failures = verify_export(export, requests, checklist)
    assert any("R5" in f and "missing" in f for f in failures)


def test_an_altered_officer_quote_is_caught(corpus):
    requests, checklist = corpus
    export = drafted(build_skeleton(requests, checklist))
    export = export.replace("legible copy", "unquestionable copy")
    failures = verify_export(export, requests, checklist)
    assert any("officer quote was altered" in f for f in failures)


def test_drafting_away_the_gap_language_is_caught(corpus):
    requests, checklist = corpus
    export = drafted(build_skeleton(requests, checklist))
    export = export.replace("not provided", "fully documented")
    export = export.replace("attorney confirmation", "our records")
    failures = verify_export(export, requests, checklist)
    assert failures != []


def all_answered(checklist):
    return [
        ChecklistRow(
            request_id=row.request_id,
            title=row.title,
            coverage=Coverage.ANSWERED,
            matches=row.matches,
            reason="petition material found",
        )
        for row in checklist
    ]


def test_a_gap_row_stripped_of_its_own_language_is_named_even_when_the_table_still_labels_it(
    corpus,
):
    # the coverage table always spells out "Not provided — needs attorney
    # confirmation", so a document-wide search can never notice that R5's
    # own section lost the warning
    requests, checklist = corpus
    export = drafted(build_skeleton(requests, checklist)).replace(NOT_PROVIDED_GAP, "")
    assert "not provided — needs attorney confirmation" in export.lower()

    failures = verify_export(export, requests, checklist)

    gap_failures = [f for f in failures if "evidence-gap" in f]
    assert len(gap_failures) == 1
    assert "R5" in gap_failures[0]


def test_every_row_stripped_of_its_gap_language_is_named_not_only_the_first(corpus):
    requests, checklist = corpus
    export = drafted(build_skeleton(requests, checklist))
    export = export.replace(NOT_PROVIDED_GAP, "").replace(PARTIAL_GAP, "")

    failures = verify_export(export, requests, checklist)

    gap_failures = [f for f in failures if "evidence-gap" in f]
    assert len(gap_failures) == 2
    assert {"R4", "R5"} == {f.split("'")[0] for f in gap_failures}


def test_a_partial_row_passes_on_its_own_gap_line_without_saying_not_provided(corpus):
    requests, checklist = corpus
    export = drafted(build_skeleton(requests, checklist))
    r4_section = response_slices(export)["R4"]
    assert "attorney confirmation" in r4_section
    assert "not provided" not in r4_section.lower()

    assert verify_export(export, requests, checklist) == []


def test_an_all_answered_export_passes_verification(corpus):
    requests, checklist = corpus
    answered = all_answered(checklist)
    export = drafted(build_skeleton(requests, answered))

    assert verify_export(export, requests, answered) == []


def test_a_gap_case_that_lost_the_phrase_from_its_own_section_still_fails(corpus):
    requests, checklist = corpus
    export = drafted(build_skeleton(requests, checklist)).replace(
        "The required evidence is not provided", "The evidence is on file"
    )

    failures = verify_export(export, requests, checklist)

    assert any("R5" in f and "evidence-gap" in f for f in failures)
