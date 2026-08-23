"""Draft → decide lifecycle, driven through rfe.py with a fake transport.

No network call is made anywhere here: the client is built with an
injected transport and `export_document` (which talks to urllib directly)
is replaced per test with the exact markdown that test wants verified.
"""
import json
import shutil

import pytest

import rfe
from engine.coverage_checklist import build_checklist
from engine.response_skeleton import build_skeleton
from superdocs.client import OperationBudget, SuperDocsClient

CASE = rfe.ROOT / "data"
JOB_ID = "job-1"


def judge_reply(buckets: dict[str, str]) -> str:
    return json.dumps(
        {
            request_id: {"coverage": coverage, "reason": "fixture verdict"}
            for request_id, coverage in buckets.items()
        }
    )


def fake_transport(calls, job_status="awaiting_approval", pending=None, reply=""):
    def transport(method, path, body):
        calls.append({"method": method, "path": path, "body": body})
        if path.startswith("/attachments/status/"):
            return {"total_ready": 5, "total_processing": 0}
        if path.startswith("/jobs/"):
            return {
                "job_id": path.rsplit("/", 1)[1],
                "status": job_status,
                "metadata": {"pending_changes": pending or []},
            }
        if path == "/chat":
            return {"response": reply}
        if path == "/chat/async":
            return {"job_id": JOB_ID}
        return {}

    return transport


def install(monkeypatch, tmp_path, transport, max_ops=5):
    client = SuperDocsClient("sk_test_fixture", OperationBudget(max_ops), transport)
    monkeypatch.setattr(rfe, "make_client", lambda: client)
    monkeypatch.setattr(rfe, "OUT", tmp_path)
    monkeypatch.setattr(rfe, "STATE_FILE", tmp_path / "run_state.json")
    return client


def lexical_case():
    requests, _, config, matches, _skipped = rfe.load_case(CASE)
    return requests, build_checklist(requests, matches, config)


def drafted(skeleton: str) -> str:
    import re

    return re.sub(
        r"\[DRAFT RESPONSE FOR R\d+ — TO BE WRITTEN\]",
        "The petition provides the requested material.",
        skeleton,
    )


def stage_decide(monkeypatch, tmp_path, export_text, checklist_rows, job_status="completed"):
    """Put a finished run on disk and hand decide_core a chosen export."""
    calls = []
    client = install(monkeypatch, tmp_path, fake_transport(calls, job_status=job_status))
    monkeypatch.setattr(
        client, "export_document", lambda session_id, format: export_text.encode("utf-8")
    )
    state = {
        "session_id": "session-1",
        "job_id": JOB_ID,
        "case_dir": str(CASE),
        "checklist": checklist_rows,
    }
    (tmp_path / "run_state.json").write_text(json.dumps(state), encoding="utf-8")
    (tmp_path / "pending_changes.json").write_text(
        json.dumps([{"change_id": "c1"}]), encoding="utf-8"
    )
    return calls, client


def test_decide_verifies_against_the_judged_checklist_not_a_lexical_rebuild(
    monkeypatch, tmp_path
):
    # the locator calls R2 answered, so a document built from its buckets
    # carries no gap language for R2; the judge disagreed and said the
    # evidence is missing, and that verdict is what the export must honour
    requests, lexical = lexical_case()
    export = drafted(build_skeleton(requests, lexical))
    judged_rows = [
        {"id": "R1", "coverage": "answered", "reason": "fixture"},
        {"id": "R2", "coverage": "not_provided", "reason": "fixture"},
        {"id": "R3", "coverage": "answered", "reason": "fixture"},
        {"id": "R4", "coverage": "partial", "reason": "fixture"},
        {"id": "R5", "coverage": "not_provided", "reason": "fixture"},
    ]
    stage_decide(monkeypatch, tmp_path, export, judged_rows)

    result = rfe.decide_core(approve_all=True)

    assert result["filed_ready"] is False
    assert any("R2" in failure for failure in result["verification_failures"])


def lexical_rows(checklist):
    return [
        {"id": row.request_id, "coverage": row.coverage.value, "reason": row.reason}
        for row in checklist
    ]


def test_a_clean_export_passes_the_citation_check(monkeypatch, tmp_path):
    requests, lexical = lexical_case()
    export = drafted(build_skeleton(requests, lexical))
    stage_decide(monkeypatch, tmp_path, export, lexical_rows(lexical))

    result = rfe.decide_core(approve_all=True)

    assert result["verification_failures"] == []
    assert result["filed_ready"] is True


def test_an_altered_petition_quote_refuses_the_export_naming_the_section(
    monkeypatch, tmp_path
):
    requests, lexical = lexical_case()
    export = drafted(build_skeleton(requests, lexical)).replace(
        "report directly to Ms. Dana Whitfield",
        "report directly to Ms. Dana Whitmore",
    )
    stage_decide(monkeypatch, tmp_path, export, lexical_rows(lexical))

    result = rfe.decide_core(approve_all=True)

    assert result["filed_ready"] is False
    assert any(
        "Response to Request 3" in failure and "02-employer-support-letter.md" in failure
        for failure in result["verification_failures"]
    )


def test_a_cited_file_outside_the_petition_is_called_invented(monkeypatch, tmp_path):
    requests, lexical = lexical_case()
    export = drafted(build_skeleton(requests, lexical)).replace(
        "`04-beneficiary-credentials.md`", "`expert-opinion-letter.md`"
    )
    stage_decide(monkeypatch, tmp_path, export, lexical_rows(lexical))

    result = rfe.decide_core(approve_all=True)

    assert result["filed_ready"] is False
    assert any("invented" in failure for failure in result["verification_failures"])


def pending_run_state(tmp_path, case_dir):
    state = {
        "session_id": "session-1",
        "job_id": "J77",
        "case_dir": str(case_dir),
        "checklist": [],
    }
    state_file = tmp_path / "run_state.json"
    state_file.write_text(json.dumps(state), encoding="utf-8")
    return state_file


def test_drafting_another_case_while_a_run_is_pending_refuses_instead_of_resuming_it(
    monkeypatch, tmp_path
):
    other_case = tmp_path / "other-case"
    state_file = pending_run_state(tmp_path, CASE)
    before = state_file.read_text(encoding="utf-8")
    calls = []
    install(monkeypatch, tmp_path, fake_transport(calls))

    with pytest.raises(ValueError) as refusal:
        rfe.draft_core(other_case)

    message = str(refusal.value)
    assert CASE.name in message and "other-case" in message
    assert "J77" in message and "decide" in message
    assert "python rfe.py" not in message
    assert state_file.read_text(encoding="utf-8") == before
    assert calls == []


def test_drafting_the_same_case_still_resumes_without_paying_again(
    monkeypatch, tmp_path
):
    pending_run_state(tmp_path, CASE)
    calls = []
    client = install(monkeypatch, tmp_path, fake_transport(calls))

    result = rfe.draft_core(CASE)

    assert result["status"] == "awaiting_approval"
    assert result["job_id"] == "J77"
    assert client.budget.spent == 0
    assert [call["path"] for call in calls] == ["/jobs/J77"]


ALL_ANSWERED = {
    "R1": "answered",
    "R2": "answered",
    "R3": "answered",
    "R4": "partial",
    "R5": "not_provided",
}


@pytest.mark.parametrize("dead_status", ["failed", "cancelled"])
def test_a_job_the_server_calls_dead_clears_the_run_state(
    monkeypatch, tmp_path, dead_status
):
    calls = []
    install(
        monkeypatch,
        tmp_path,
        fake_transport(calls, job_status=dead_status, reply=judge_reply(ALL_ANSWERED)),
    )

    result = rfe.draft_core(CASE)

    assert result["status"] == dead_status
    assert not (tmp_path / "run_state.json").exists()
    assert any(
        dead_status in note and "starts fresh" in note for note in result["notes"]
    )


def test_a_poll_timeout_keeps_the_run_state_because_the_job_may_still_live(
    monkeypatch, tmp_path
):
    from superdocs.errors import TransportError

    calls = []
    install(
        monkeypatch,
        tmp_path,
        fake_transport(calls, job_status="processing", reply=judge_reply(ALL_ANSWERED)),
    )
    monkeypatch.setattr(rfe, "MAX_JOB_WAIT_SECONDS", 0)

    with pytest.raises(TransportError):
        rfe.draft_core(CASE)

    assert (tmp_path / "run_state.json").exists()


def test_a_job_that_dies_during_decide_clears_the_run_state_too(monkeypatch, tmp_path):
    requests, lexical = lexical_case()
    stage_decide(
        monkeypatch, tmp_path, "", lexical_rows(lexical), job_status="failed"
    )

    result = rfe.decide_core(approve_all=True)

    assert result["status"] == "failed"
    assert not (tmp_path / "run_state.json").exists()
    assert any("starts fresh" in note for note in result["notes"])


def test_draft_saves_the_judged_checklist_into_the_run_state(monkeypatch, tmp_path):
    requests, _ = lexical_case()
    buckets = {
        "R1": "answered",
        "R2": "not_provided",
        "R3": "answered",
        "R4": "partial",
        "R5": "not_provided",
    }
    calls = []
    install(
        monkeypatch,
        tmp_path,
        fake_transport(calls, reply=judge_reply(buckets)),
    )

    rfe.draft_core(CASE)

    state = json.loads((tmp_path / "run_state.json").read_text(encoding="utf-8"))
    saved = {row["id"]: row["coverage"] for row in state["checklist"]}
    assert saved == buckets


def review_file_for(monkeypatch, tmp_path, change: dict) -> str:
    monkeypatch.setattr(rfe, "OUT", tmp_path)
    rfe.dump_pending_changes({"metadata": {"pending_changes": [change]}})
    return (tmp_path / "pending_changes.md").read_text(encoding="utf-8")


def test_a_change_too_long_for_the_review_file_says_where_it_was_cut(
    monkeypatch, tmp_path
):
    review = review_file_for(
        monkeypatch, tmp_path, {"change_id": "c1", "new_html": "<p>x</p>" * 600}
    )

    assert rfe.CUT_SHORT_MARKER in review


def test_a_change_that_fits_the_review_file_carries_no_cut_marker(
    monkeypatch, tmp_path
):
    review = review_file_for(
        monkeypatch,
        tmp_path,
        {"change_id": "c1", "old_html": "<p>o</p>" * 30, "new_html": "<p>n</p>" * 30},
    )

    assert rfe.CUT_SHORT_MARKER not in review


def session_ids_seen(calls) -> list[str]:
    seen = []
    for call in calls:
        if call["path"].startswith("/attachments/status/"):
            seen.append(call["path"].rsplit("/", 1)[1])
        body = call["body"] or {}
        if "session_id" in body:
            seen.append(body["session_id"])
    return seen


def test_a_case_folder_named_with_a_space_still_gets_url_safe_session_ids(
    monkeypatch, tmp_path
):
    case = tmp_path / "Client Smith"
    shutil.copytree(CASE, case)
    calls = []
    install(
        monkeypatch, tmp_path, fake_transport(calls, reply=judge_reply(ALL_ANSWERED))
    )

    rfe.draft_core(case)

    seen = session_ids_seen(calls)
    assert seen
    for session_id in seen:
        assert " " not in session_id
        assert "Client" not in session_id


def test_two_fresh_drafts_of_one_case_do_not_reuse_the_same_session_id(
    monkeypatch, tmp_path
):
    first, second = [], []
    install(
        monkeypatch, tmp_path, fake_transport(first, reply=judge_reply(ALL_ANSWERED))
    )
    rfe.draft_core(CASE)
    (tmp_path / "run_state.json").unlink()
    install(
        monkeypatch, tmp_path, fake_transport(second, reply=judge_reply(ALL_ANSWERED))
    )
    rfe.draft_core(CASE)

    assert session_ids_seen(first)[0] != session_ids_seen(second)[0]


def case_with_a_legacy_doc(tmp_path):
    case = tmp_path / "case-with-a-legacy-doc"
    shutil.copytree(CASE, case)
    (case / "petition" / "02-support-letter.doc").write_bytes(b"legacy word bytes")
    return case


def test_a_petition_file_in_an_unsupported_format_is_skipped_and_named(
    monkeypatch, tmp_path
):
    case = case_with_a_legacy_doc(tmp_path)
    calls = []
    install(
        monkeypatch, tmp_path, fake_transport(calls, reply=judge_reply(ALL_ANSWERED))
    )

    result = rfe.draft_core(case)

    assert result["status"] == "awaiting_approval"
    assert result["skipped_files"] == ["02-support-letter.doc"]
    assert any(
        "02-support-letter.doc" in note and "format not supported" in note
        for note in result["notes"]
    )
    uploaded = [
        call["body"]["filename"]
        for call in calls
        if call["path"] == "/attachments/upload-base64"
    ]
    assert uploaded
    assert "02-support-letter.doc" not in uploaded


def test_the_preview_checklist_names_the_petition_files_it_could_not_read(
    monkeypatch, tmp_path
):
    case = case_with_a_legacy_doc(tmp_path)
    monkeypatch.setattr(rfe, "OUT", tmp_path)

    result = rfe.preview_core(case)

    assert result["skipped_files"] == ["02-support-letter.doc"]
    checklist = (tmp_path / "checklist.md").read_text(encoding="utf-8")
    assert "skipped, format not supported: 02-support-letter.doc" in checklist


def test_a_preview_with_nothing_skipped_says_nothing_about_skipped_files(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(rfe, "OUT", tmp_path)

    result = rfe.preview_core(CASE)

    assert result["skipped_files"] == []
    assert "skipped" not in (tmp_path / "checklist.md").read_text(encoding="utf-8")


def test_a_deleted_citation_refuses_the_export_naming_the_request(
    monkeypatch, tmp_path
):
    requests, lexical = lexical_case()
    lines = drafted(build_skeleton(requests, lexical)).splitlines()
    # the first citation of this file sits in R1's section; deleting the
    # citation line and its quote line must be caught and blamed on R1
    cite = next(
        i for i, line in enumerate(lines) if "02-employer-support-letter.md" in line
    )
    del lines[cite : cite + 2]
    stage_decide(monkeypatch, tmp_path, "\n".join(lines), lexical_rows(lexical))

    result = rfe.decide_core(approve_all=True)

    assert result["filed_ready"] is False
    assert any(
        "R1" in failure and "removed" in failure
        for failure in result["verification_failures"]
    )


def test_an_angle_bracket_inserted_into_a_quote_is_caught(monkeypatch, tmp_path):
    requests, lexical = lexical_case()
    export = drafted(build_skeleton(requests, lexical)).replace(
        "report directly to Ms. Dana Whitfield",
        "report directly to > Ms. Dana Whitfield",
    )
    stage_decide(monkeypatch, tmp_path, export, lexical_rows(lexical))

    result = rfe.decide_core(approve_all=True)

    assert result["filed_ready"] is False
    assert any(
        "Response to Request 3" in failure
        for failure in result["verification_failures"]
    )


def pending_run_state_with_spent(tmp_path, spent):
    state = {
        "session_id": "session-1",
        "job_id": "J77",
        "case_dir": str(CASE),
        "checklist": [
            {"id": rid, "coverage": cov, "reason": "fixture"}
            for rid, cov in ALL_ANSWERED.items()
        ],
    }
    if spent is not None:
        state["ops_spent"] = spent
    (tmp_path / "run_state.json").write_text(json.dumps(state), encoding="utf-8")
    (tmp_path / "pending_changes.json").write_text(
        json.dumps([{"change_id": "c1"}]), encoding="utf-8"
    )


def test_a_fresh_draft_saves_what_it_spent_into_the_run_state(monkeypatch, tmp_path):
    calls = []
    install(monkeypatch, tmp_path, fake_transport(calls, reply=judge_reply(ALL_ANSWERED)))

    result = rfe.draft_core(CASE)

    state = json.loads((tmp_path / "run_state.json").read_text(encoding="utf-8"))
    # this transport sends no usage block, so each billable call (the judge
    # question, the async draft) counts its floor of one
    assert result["ops_spent"] == 2
    assert state["ops_spent"] == 2


def test_decide_continues_the_count_the_draft_left(monkeypatch, tmp_path):
    # the run's counter spans draft → decide → decide: a decide that opens a
    # new review round must report and save the running total, not zero
    pending_run_state_with_spent(tmp_path, spent=3)
    calls = []
    install(monkeypatch, tmp_path, fake_transport(calls, pending=[{"change_id": "c2"}]))

    result = rfe.decide_core(approve_all=True)

    assert result["status"] == "awaiting_approval"
    assert result["ops_spent"] == 3
    state = json.loads((tmp_path / "run_state.json").read_text(encoding="utf-8"))
    assert state["ops_spent"] == 3


def test_a_resumed_draft_continues_the_count_too(monkeypatch, tmp_path):
    pending_run_state_with_spent(tmp_path, spent=2)
    calls = []
    install(monkeypatch, tmp_path, fake_transport(calls))

    result = rfe.draft_core(CASE)

    assert result["ops_spent"] == 2
    assert [call["path"] for call in calls] == ["/jobs/J77"]


def test_a_run_state_written_before_the_count_existed_reads_as_zero(
    monkeypatch, tmp_path
):
    pending_run_state_with_spent(tmp_path, spent=None)
    calls = []
    install(monkeypatch, tmp_path, fake_transport(calls, pending=[{"change_id": "c2"}]))

    result = rfe.decide_core(approve_all=True)

    assert result["ops_spent"] == 0


def test_a_run_at_the_cap_refuses_the_next_billable_call(monkeypatch, tmp_path):
    # the cap is checked against the whole run's count, so a draft that
    # starts with the cap already spent is refused before anything is sent
    from superdocs.errors import BudgetExceeded

    pending_run_state_with_spent(tmp_path, spent=5)
    (tmp_path / "run_state.json").unlink()  # fresh draft, but a pre-spent budget
    calls = []
    client = install(monkeypatch, tmp_path, fake_transport(calls), max_ops=5)
    client.budget.spent = 5

    with pytest.raises(BudgetExceeded):
        rfe.draft_core(CASE)

    assert not any(call["path"] == "/chat/async" for call in calls)
