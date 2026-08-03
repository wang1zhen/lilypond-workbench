from __future__ import annotations

import re
from pathlib import Path

from .common import Diagnostic


LOCATION_RE = re.compile(r"^(?P<file>.*?):(?P<line>\d+):(?P<column>\d+):\s*(?P<body>.*)$")
SEVERITY_RE = re.compile(r"\b(?P<severity>fatal error|error|warning):\s*(?P<message>.*)", re.IGNORECASE)


def _classify(message: str, severity: str) -> tuple[str, str | None]:
    lower = message.lower()
    if "bar check failed" in lower or "measure length" in lower:
        return "BAR_DURATION", "Check note and rest durations against the active time signature."
    if "syntax error" in lower or "unexpected" in lower:
        return "SYNTAX_ERROR", "Inspect braces, << >>, slurs, ties, and the preceding line."
    if "cannot find file" in lower or "failed files" in lower:
        return "INCLUDE_NOT_FOUND", "Correct the include path relative to the compiled source."
    if "unknown escaped string" in lower:
        return "UNKNOWN_COMMAND", "Check the LilyPond command spelling and version compatibility."
    if "not a note name" in lower:
        return "INVALID_PITCH", "Check the selected pitch language and note spelling."
    if "guile" in lower or "scheme" in lower:
        return "SCHEME_ERROR", "Review Scheme quoting, parentheses, and argument types."
    if "lyrics" in lower and ("align" in lower or "syllable" in lower):
        return "LYRICS_ALIGNMENT", "Match lyric syllables to note events; use -- and __ where appropriate."
    if "unterminated" in lower or "unmatched" in lower:
        return "UNMATCHED_DELIMITER", "Balance braces, angle brackets, parentheses, and quoted strings."
    return ("LILYPOND_ERROR" if severity == "error" else "LILYPOND_WARNING", None)


def parse_lilypond_log(text: str) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    last_location: tuple[str | None, int | None, int | None] = (None, None, None)
    seen: set[tuple[str, str | None, int | None, str]] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("Fontconfig error:") and "No writable cache directories" in line:
            key = ("FONT_CACHE_UNWRITABLE", None, None, line)
            if key not in seen:
                seen.add(key)
                diagnostics.append(
                    Diagnostic(
                        "warning",
                        "FONT_CACHE_UNWRITABLE",
                        "Fontconfig cache is not writable; rendering continued without a persistent font cache",
                    )
                )
            continue
        location = LOCATION_RE.match(line)
        body = line
        if location:
            last_location = (
                str(Path(location.group("file")).expanduser()),
                int(location.group("line")),
                int(location.group("column")),
            )
            body = location.group("body")
        severity_match = SEVERITY_RE.search(body)
        if not severity_match:
            if "bar check failed" not in body.lower():
                continue
            severity, message = "warning", body
        else:
            severity = "error" if "error" in severity_match.group("severity").lower() else "warning"
            message = severity_match.group("message").strip()
        code, suggestion = _classify(message, severity)
        file_name, line_no, column = last_location
        key = (code, file_name, line_no, message)
        if key in seen:
            continue
        seen.add(key)
        diagnostics.append(
            Diagnostic(
                severity=severity,
                code=code,
                message=message,
                file=file_name,
                line=line_no,
                column=column,
                suggestion=suggestion,
            )
        )
    return diagnostics
