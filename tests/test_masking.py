"""Invariants for masked_source().

Every regex scan in this package runs against the mask and then indexes back
into the original text, so a single dropped or added character silently shifts
every reported line number.  A wrong mask does not fail a render; it just makes
diagnostics point at the wrong place.  These tests pin the invariants that make
the offset round-trip safe:

1. mask[i] is either text[i] or a space -- nothing is inserted, deleted, or
   substituted for a different character.
2. newlines survive at exactly their original offsets, so line numbers hold.
3. comment and string payloads are blanked, so their contents cannot be matched
   as code.
4. code outside comments and strings is untouched.
"""

from __future__ import annotations

import random

import pytest

from lilypond_workbench.syntax import masked_source


CASES = {
    "plain": '\\version "2.24.4"\nmelody = { c4 d e f }\n',
    "line_comment": "melody = { c4 } % a { brace } in a comment\nnext = { d4 }\n",
    "comment_at_eof": "melody = { c4 } % trailing comment without a newline",
    "block_comment": "a = { c4 }\n%{ commented { out }\nstill { commented }\n%}\nb = { d4 }\n",
    "block_comment_unterminated": "a = { c4 }\n%{ never closed { \n",
    "nested_percent_in_block": "%{ 50% off { }\n%}\na = { c4 }\n",
    "string_with_brace": 'header = { title = "Sonata { in } C" }\n',
    "string_with_percent": 'header = { title = "100% acoustic" }\n',
    "escaped_quote": 'header = { title = "a \\"quoted\\" word" }\n',
    "escaped_backslash": 'header = { subtitle = "back\\\\slash" }\n',
    "unterminated_string": 'header = { title = "no closing quote\n',
    "escaped_newline_in_string": 'a = { c4 }\n"open \\\nb = { d4 }\n',
    "comment_then_string": '% "not a string"\nheader = { title = "real" }\n',
    "string_then_comment": 'title = "%{ not a comment"\na = { c4 }\n',
    "empty": "",
    "only_newlines": "\n\n\n",
    "crlf": 'a = { c4 }\r\n% comment\r\nb = { d4 }\r\n',
    "unicode": 'header = { composer = "巴赫" }\n% 注释 { }\na = { c4 }\n',
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_mask_only_ever_blanks_characters(name: str) -> None:
    text = CASES[name]
    mask = masked_source(text)
    assert len(mask) == len(text)
    mismatched = [
        (index, text[index], mask[index])
        for index in range(len(text))
        if mask[index] not in (text[index], " ")
    ]
    assert not mismatched


@pytest.mark.parametrize("name", sorted(CASES))
def test_newline_offsets_are_preserved(name: str) -> None:
    text = CASES[name]
    mask = masked_source(text)
    assert [i for i, c in enumerate(mask) if c == "\n"] == [i for i, c in enumerate(text) if c == "\n"]


@pytest.mark.parametrize("name", sorted(CASES))
def test_mask_never_introduces_structural_characters(name: str) -> None:
    """Braces, angle brackets, quotes, and backslashes may vanish, never appear."""
    text = CASES[name]
    mask = masked_source(text)
    for index, char in enumerate(mask):
        if char in '{}<>"\\%':
            assert text[index] == char, f"{name}: mask invented {char!r} at {index}"


@pytest.mark.parametrize("name", sorted(CASES))
def test_masking_is_idempotent(name: str) -> None:
    mask = masked_source(CASES[name])
    assert masked_source(mask) == mask


def test_comment_payloads_are_blanked() -> None:
    text = CASES["line_comment"]
    mask = masked_source(text)
    comment_start = text.index("%")
    comment_end = text.index("\n", comment_start)
    assert mask[comment_start:comment_end].strip() == ""
    assert mask[:comment_start] == text[:comment_start]
    assert mask[comment_end:] == text[comment_end:]


def test_block_comment_payload_is_blanked_but_keeps_its_lines() -> None:
    text = CASES["block_comment"]
    mask = masked_source(text)
    start = text.index("%{")
    end = text.index("%}") + 2
    assert mask[start:end].replace("\n", "").strip() == ""
    assert mask.count("\n") == text.count("\n")
    assert "b = { d4 }" in mask


def test_string_payload_is_blanked_including_its_quotes() -> None:
    text = CASES["string_with_brace"]
    mask = masked_source(text)
    start = text.index('"')
    end = text.rindex('"') + 1
    assert mask[start:end].strip() == ""
    assert mask.count("{") == 1 and mask.count("}") == 1


def test_escaped_quote_does_not_end_the_string_early() -> None:
    text = 'title = "a \\"{\\" word" % real comment { }\na = { c4 }\n'
    mask = masked_source(text)
    # Only the genuine music braces survive.
    assert [index for index, char in enumerate(mask) if char == "{"] == [text.index("{ c4 }")]


def test_percent_inside_a_string_does_not_start_a_comment() -> None:
    mask = masked_source(CASES["string_with_percent"])
    assert "acoustic" not in mask
    assert mask.count("}") == 1


def test_quote_inside_a_comment_does_not_start_a_string() -> None:
    text = CASES["comment_then_string"]
    mask = masked_source(text)
    assert "header = { title = " in mask
    assert "real" not in mask


def test_a_backslash_at_end_of_line_keeps_the_newline() -> None:
    """Regression: blanking an escaped newline shifted every later line number."""
    text = 'a = { c4 }\n"open \\\nb = { d4 }\n'
    mask = masked_source(text)
    assert mask.count("\n") == text.count("\n")
    assert mask.index("\n") == text.index("\n")


def _random_source(rng: random.Random) -> str:
    """Assemble a source out of fragments that stress every masking state."""
    fragments = [
        "a = { c4 d e f }\n",
        "b = \\relative c' { g4 a b c }\n",
        "% comment with { } and \" and %{\n",
        "%{ block { } \" comment %}\n",
        '"a string { } % with escapes \\" and \\\\"\n',
        '\\header { title = "T" composer = "C" }\n',
        "%",
        '"',
        "%{",
        "%}",
        "\\",
        "\n",
        "{",
        "}",
        " ",
        "巴赫",
    ]
    return "".join(rng.choice(fragments) for _ in range(rng.randint(1, 40)))


@pytest.mark.parametrize("seed", range(200))
def test_invariants_hold_on_generated_sources(seed: int) -> None:
    """Fuzz with a fixed seed range so failures are reproducible."""
    text = _random_source(random.Random(seed))
    mask = masked_source(text)
    assert len(mask) == len(text)
    assert [i for i, c in enumerate(mask) if c == "\n"] == [i for i, c in enumerate(text) if c == "\n"]
    for index, char in enumerate(mask):
        assert char == text[index] or char == " "
    assert masked_source(mask) == mask
