from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import ly.document
import ly.indent
import ly.reformat

from .common import Diagnostic, WorkbenchError


@dataclass(slots=True)
class Block:
    command_start: int
    open_brace: int
    close_brace: int


@dataclass(slots=True)
class MusicVariable:
    name: str
    start: int
    open_brace: int
    close_brace: int
    line: int


def masked_source(text: str) -> str:
    """Mask comments and strings while preserving offsets and newlines."""
    chars = list(text)
    i = 0
    state = "normal"
    while i < len(chars):
        char = chars[i]
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        if state == "normal":
            if char == "%" and nxt == "{":
                chars[i] = chars[i + 1] = " "
                i += 2
                state = "block_comment"
                continue
            if char == "%":
                chars[i] = " "
                state = "line_comment"
            elif char == '"':
                chars[i] = " "
                state = "string"
        elif state == "line_comment":
            if char == "\n":
                state = "normal"
            else:
                chars[i] = " "
        elif state == "block_comment":
            if char == "%" and nxt == "}":
                chars[i] = chars[i + 1] = " "
                i += 2
                state = "normal"
                continue
            if char != "\n":
                chars[i] = " "
        elif state == "string":
            if char == "\\" and nxt:
                chars[i] = chars[i + 1] = " "
                i += 2
                continue
            if char == '"':
                state = "normal"
            if char != "\n":
                chars[i] = " "
        i += 1
    return "".join(chars)


def matching_brace(masked: str, open_brace: int) -> int:
    depth = 0
    for pos in range(open_brace, len(masked)):
        if masked[pos] == "{":
            depth += 1
        elif masked[pos] == "}":
            depth -= 1
            if depth == 0:
                return pos
    raise WorkbenchError("Unmatched opening brace in LilyPond source", "UNMATCHED_DELIMITER")


def find_command_blocks(text: str, command: str, *, top_level_only: bool = False) -> list[Block]:
    masked = masked_source(text)
    pattern = re.compile(rf"\\{re.escape(command)}\b")
    blocks: list[Block] = []
    for match in pattern.finditer(masked):
        if top_level_only:
            depth = masked[: match.start()].count("{") - masked[: match.start()].count("}")
            if depth != 0:
                continue
        open_brace = masked.find("{", match.end())
        if open_brace < 0:
            continue
        blocks.append(Block(match.start(), open_brace, matching_brace(masked, open_brace)))
    return blocks


VARIABLE_RE = re.compile(
    r"(?m)^(?P<indent>\s*)(?P<name>[A-Za-z][A-Za-z0-9_-]*)\s*=\s*"
    r"(?:(?:\\(?:relative|absolute|fixed|transpose|drummode|chordmode|figuremode)\b)[^{]*)?\{"
)


def extract_music_variables(text: str) -> list[MusicVariable]:
    masked = masked_source(text)
    variables: list[MusicVariable] = []
    for match in VARIABLE_RE.finditer(masked):
        open_brace = masked.find("{", match.start(), match.end() + 1)
        if open_brace < 0:
            continue
        close_brace = matching_brace(masked, open_brace)
        variables.append(
            MusicVariable(
                name=match.group("name"),
                start=match.start(),
                open_brace=open_brace,
                close_brace=close_brace,
                line=text[: match.start()].count("\n") + 1,
            )
        )
    return variables


def sanitize_definitions(text: str) -> str:
    blocks: list[Block] = []
    for command in ("score", "book", "bookpart"):
        blocks.extend(find_command_blocks(text, command, top_level_only=True))
    if not blocks:
        return text
    spans = sorted(((item.command_start, item.close_brace + 1) for item in blocks), reverse=True)
    output = text
    for start, end in spans:
        output = output[:start] + "% score assembly removed by lilypond-workbench\n" + output[end:]
    return output


def insert_midi_block(text: str, score_index: int = 0) -> str:
    scores = find_command_blocks(text, "score")
    if not scores:
        raise WorkbenchError("No \\score block found for MIDI analysis", "SCORE_NOT_FOUND")
    if score_index < 0 or score_index >= len(scores):
        raise WorkbenchError(
            f"Score index {score_index} is out of range; file contains {len(scores)} score block(s)",
            "SCORE_INDEX",
            exit_code=2,
        )
    selected = scores[score_index]
    content = masked_source(text[selected.open_brace : selected.close_brace + 1])
    if re.search(r"\\midi\b", content):
        return text
    indent_start = text.rfind("\n", 0, selected.close_brace) + 1
    indent = re.match(r"\s*", text[indent_start:selected.close_brace]).group(0)
    insertion = f"\n{indent}  \\midi {{ }}\n{indent}"
    return text[: selected.close_brace] + insertion + text[selected.close_brace :]


def reformat_lilypond(text: str) -> str:
    document = ly.document.Document(text, mode="lilypond")
    cursor = ly.document.Cursor(document)
    cursor.select_all()
    indenter = ly.indent.Indenter()
    indenter.indentwidth = 2
    ly.reformat.reformat(cursor, indenter)
    output = document.plaintext()
    return output.rstrip() + "\n"


def rewrite_relative_includes(text: str, source_dir: Path) -> str:
    pattern = re.compile(r'(\\include\s+")([^"\n]+)(")')

    def replace(match: re.Match[str]) -> str:
        path = Path(match.group(2))
        if path.is_absolute():
            return match.group(0)
        return f'{match.group(1)}{(source_dir / path).resolve().as_posix()}{match.group(3)}'

    return pattern.sub(replace, text)


NOTE_RE = re.compile(
    r"(?P<chord><[^>]+>|(?<![A-Za-z\\])(?:[a-g](?:is|es|isis|eses)?[,']*|[rRsq])(?![A-Za-z]))"
    r"(?P<duration>\d+)?(?P<dots>\.*)(?:\*(?P<mult_num>\d+)(?:/(?P<mult_den>\d+))?)?"
)
TIME_RE = re.compile(r"\\time\s+(\d+)\s*/\s*(\d+)")
PARTIAL_RE = re.compile(r"\\partial\s+(\d+)(\.*)")
TUPLET_RE = re.compile(r"\\(?:tuplet|times)\s+(\d+)\s*/\s*(\d+)\s*\{")


def _duration(denominator: int, dots: int, multiplier: Fraction = Fraction(1)) -> Fraction:
    value = Fraction(1, denominator)
    addition = value
    for _ in range(dots):
        addition /= 2
        value += addition
    return value * multiplier


def check_measure_durations(text: str, *, file_name: str | None = None) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    variables = extract_music_variables(text)
    if not variables:
        variables = [MusicVariable("document", 0, 0, len(text) - 1, 1)]
    global_meter = Fraction(1, 1)
    global_partial: Fraction | None = None
    global_variable = next((item for item in variables if item.name == "global"), None)
    if global_variable is not None:
        global_body = text[global_variable.open_brace + 1 : global_variable.close_brace]
        global_time_match = TIME_RE.search(masked_source(global_body))
        if global_time_match:
            global_meter = Fraction(int(global_time_match.group(1)), int(global_time_match.group(2)))
        global_partial_match = PARTIAL_RE.search(masked_source(global_body))
        if global_partial_match:
            global_partial = _duration(int(global_partial_match.group(1)), len(global_partial_match.group(2)))
    for variable in variables:
        if variable.name == "global":
            continue
        body = text[variable.open_brace + 1 : variable.close_brace]
        masked = masked_source(body)
        declaration = masked_source(text[variable.start : variable.open_brace])
        if "\\drummode" in declaration or "\\figuremode" in declaration:
            diagnostics.append(
                Diagnostic(
                    "info",
                    "DURATION_PARTIAL_ANALYSIS",
                    f"{variable.name}: drum/figure mode requires compiler validation",
                    file=file_name,
                    line=variable.line,
                )
            )
            continue
        if "<<" in masked or re.search(r"#\s*\(", masked) or "\\compoundMeter" in masked:
            diagnostics.append(
                Diagnostic(
                    "info",
                    "DURATION_PARTIAL_ANALYSIS",
                    f"{variable.name}: simultaneous music or Scheme requires compiler validation",
                    file=file_name,
                    line=variable.line,
                )
            )
            continue
        masked = re.sub(
            r"\\(?:key|transposition)\s+[a-g](?:is|es|isis|eses)?[,']*(?:\s+\\(?:major|minor))?",
            " ",
            masked,
        )
        meter = global_meter
        partial = global_partial if "\\global" in masked else None
        accumulated = Fraction(0)
        inherited = 4
        bar = 1
        scale_stack = [Fraction(1)]
        pending_scale: Fraction | None = None
        token_re = re.compile(
            rf"(?P<time>{TIME_RE.pattern})|(?P<partial>{PARTIAL_RE.pattern})|"
            rf"(?P<tuplet>{TUPLET_RE.pattern})|(?P<open>\{{)|(?P<close>\}})|(?P<bar>\|)|(?P<note>{NOTE_RE.pattern})"
        )
        for token in token_re.finditer(masked):
            kind = token.lastgroup
            if kind == "time":
                match = TIME_RE.search(token.group(0))
                meter = Fraction(int(match.group(1)), int(match.group(2)))
            elif kind == "partial":
                match = PARTIAL_RE.search(token.group(0))
                partial = _duration(int(match.group(1)), len(match.group(2)))
            elif kind == "tuplet":
                match = TUPLET_RE.search(token.group(0))
                scale_stack.append(scale_stack[-1] * Fraction(int(match.group(2)), int(match.group(1))))
                pending_scale = None
            elif kind == "open":
                scale_stack.append(scale_stack[-1] * (pending_scale or 1))
                pending_scale = None
            elif kind == "close":
                if len(scale_stack) > 1:
                    scale_stack.pop()
            elif kind == "note":
                note = NOTE_RE.search(token.group(0))
                if note.group("duration"):
                    inherited = int(note.group("duration"))
                multiplier = Fraction(
                    int(note.group("mult_num") or 1),
                    int(note.group("mult_den") or 1),
                )
                accumulated += _duration(inherited, len(note.group("dots") or ""), multiplier) * scale_stack[-1]
            elif kind == "bar" and accumulated:
                expected = partial if partial is not None and bar == 1 else meter
                if accumulated != expected:
                    line = variable.line + body[: token.start()].count("\n")
                    diagnostics.append(
                        Diagnostic(
                            "warning",
                            "BAR_DURATION",
                            f"{variable.name} bar {bar}: expected {expected}, got {accumulated} whole notes",
                            file=file_name,
                            line=line,
                            suggestion="Verify inherited durations, rests, tuplets, and the active time signature.",
                            details={"variable": variable.name, "bar": bar, "expected": str(expected), "actual": str(accumulated)},
                        )
                    )
                accumulated = Fraction(0)
                partial = None
                bar += 1
        if accumulated and accumulated != meter:
            diagnostics.append(
                Diagnostic(
                    "warning",
                    "FINAL_BAR_DURATION",
                    f"{variable.name} final bar: expected {meter}, got {accumulated} whole notes",
                    file=file_name,
                    line=variable.line + body.count("\n"),
                    suggestion="Check whether this is an intentional cadenza or incomplete final measure.",
                    details={"variable": variable.name, "bar": bar, "expected": str(meter), "actual": str(accumulated)},
                )
            )
    return diagnostics
