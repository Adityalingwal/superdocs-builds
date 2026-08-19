from engine.verify_citations import citation_is_verbatim, find_citation_failures


def test_a_real_quote_passes_whitespace_and_case_insensitively(petition):
    quote = "equivalent to a Bachelor of Science in Computer   Science"
    assert citation_is_verbatim(quote, petition["04-beneficiary-credentials.md"])


def test_a_paraphrase_is_not_a_citation(petition):
    paraphrase = "his degree is basically the same as an American one"
    assert not citation_is_verbatim(
        paraphrase, petition["04-beneficiary-credentials.md"]
    )


def test_a_fabricated_quote_fails_naming_the_section(petition):
    failures = find_citation_failures(
        [
            {
                "section": "Response to Request 1",
                "file": "04-beneficiary-credentials.md",
                "quote": "the beneficiary also holds a master's degree",
            }
        ],
        petition,
    )
    assert len(failures) == 1
    assert "Response to Request 1" in failures[0]


def test_a_citation_to_a_nonexistent_file_is_called_invented(petition):
    failures = find_citation_failures(
        [
            {
                "section": "Response to Request 2",
                "file": "expert-opinion-letter.md",
                "quote": "anything",
            }
        ],
        petition,
    )
    assert len(failures) == 1
    assert "invented" in failures[0]


def test_clean_citations_produce_no_failures(petition):
    failures = find_citation_failures(
        [
            {
                "section": "Response to Request 3",
                "file": "02-employer-support-letter.md",
                "quote": "report directly to Ms. Dana Whitfield",
            }
        ],
        petition,
    )
    assert failures == []
