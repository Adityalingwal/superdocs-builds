import re


def _normalize(text: str) -> str:
    # Markdown blockquote markers are formatting, not content: a quote taken
    # from inside a "> ..." block must still match.
    text = re.sub(r"^\s*>\s?", "", text, flags=re.MULTILINE)
    return re.sub(r"\s+", " ", text).strip().lower()


def citation_is_verbatim(quote: str, source_text: str) -> bool:
    """A cited quote must appear word-for-word in its named source.

    Comparison is whitespace- and case-insensitive, nothing more: a
    paraphrase is not a citation.
    """
    return _normalize(quote) in _normalize(source_text)


def find_citation_failures(
    cited_sections: list[dict], sources: dict[str, str]
) -> list[str]:
    """Check every drafted section's citations; name each failure.

    `cited_sections`: [{"section": ..., "file": ..., "quote": ...}, ...]
    `sources`: file name -> full text.
    Returns human-readable failure messages, empty when all citations hold.
    """
    failures = []
    for cited in cited_sections:
        section, file, quote = cited["section"], cited["file"], cited["quote"]
        if file not in sources:
            failures.append(
                f"section '{section}' cites '{file}', which is not among the "
                f"petition documents — the citation is invented"
            )
        elif not citation_is_verbatim(quote, sources[file]):
            failures.append(
                f"section '{section}' quotes text that does not appear in "
                f"'{file}' — fix the quote or the citation before export"
            )
    return failures
