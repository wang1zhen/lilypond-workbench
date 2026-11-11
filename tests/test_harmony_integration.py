import json
from pathlib import Path

import pytest

from lilypond_workbench.common import WorkbenchError
from lilypond_workbench.harmony import analyze_harmony


def _multi_score(selected_midi: bool) -> str:
    selected_midi_block = "\\midi { }" if selected_midi else "% selected score has no MIDI block"
    return rf"""\version "2.24.4"

selected = \relative c'' {{
  \time 4/4
  <a cis e>1 |
  <d fis a>1 |
  <e gis b>1 |
  <a cis e>1 |
}}

other = \relative c' {{
  \time 4/4
  <c e g>1 |
  <f a c>1 |
  <g b d>1 |
  <c e g>1 |
}}

\score {{
  \new Staff \selected
  \layout {{ }}
  {selected_midi_block}
}}

\score {{
  \new Staff \other
  \layout {{ }}
  \midi {{ }}
}}
"""


def _analyze(tmp_path: Path, text: str, score_index: int) -> set[str]:
    source = tmp_path / "multi-score.ly"
    source.write_text(text, encoding="utf-8")
    output = tmp_path / "harmony.ily"
    result = analyze_harmony(source, output_path=output, score_index=score_index, key_override="C", force=True)
    assert result.ok
    report = json.loads(output.with_suffix(".analysis.json").read_text(encoding="utf-8"))
    return {event["chord_symbol"] for event in report["events"] if event["accepted"]}


@pytest.mark.integration
@pytest.mark.parametrize("selected_midi", [False, True], ids=["selected-without-midi", "selected-with-midi"])
def test_harmony_analyzes_only_the_selected_score(tmp_path: Path, selected_midi: bool) -> None:
    symbols = _analyze(tmp_path, _multi_score(selected_midi), 0)
    assert {"A", "D", "E"} <= symbols
    assert "C" not in symbols


@pytest.mark.integration
def test_harmony_selected_score_keeps_relative_include(tmp_path: Path) -> None:
    (tmp_path / "music.inc.ly").write_text(
        "included = \\relative c'' { <a cis e>1 | <d fis a>1 | <e gis b>1 | <a cis e>1 }\n",
        encoding="utf-8",
    )
    text = (
        '\\version "2.24.4"\n'
        '\\include "music.inc.ly"\n'
        'other = \\relative c\' { <c e g>1 | <f a c>1 | <g b d>1 | <c e g>1 }\n'
        '\\score { \\new Staff \\included \\layout { } }\n'
        '\\score { \\new Staff \\other \\layout { } \\midi { } }\n'
    )
    assert {"A", "D", "E"} <= _analyze(tmp_path, text, 0)


@pytest.mark.integration
def test_harmony_refuses_include_with_another_score(tmp_path: Path) -> None:
    (tmp_path / "extra.inc.ly").write_text(
        "\\score { \\new Staff { c'1 } \\layout { } \\midi { } }\n",
        encoding="utf-8",
    )
    source = tmp_path / "main.ly"
    source.write_text(
        '\\version "2.24.4"\n'
        '\\include "extra.inc.ly"\n'
        "\\score { \\new Staff { a'1 } \\layout { } \\midi { } }\n",
        encoding="utf-8",
    )
    with pytest.raises(WorkbenchError) as exc:
        analyze_harmony(source, output_path=tmp_path / "harmony.ily", force=True)
    assert exc.value.code == "HARMONY_MIDI_AMBIGUOUS"
    assert exc.value.exit_code == 2


@pytest.mark.integration
def test_harmony_selects_last_score_after_nested_score_block(tmp_path: Path) -> None:
    text = (
        '\\version "2.24.4"\n'
        "\\score { \\new Staff { c'1^\\markup { \\score { \\new Staff { d'4 } \\layout { } } } } "
        "\\layout { } \\midi { } }\n"
        "\\score { \\new Staff { <a' cis'' e''>1 } \\layout { } \\midi { } }\n"
    )
    symbols = _analyze(tmp_path, text, 2)
    assert "A" in symbols
    assert "C" not in symbols and "D" not in symbols
