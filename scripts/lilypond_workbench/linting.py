from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from .clefs import analyze_clef_index
from .common import Diagnostic, Result, WorkbenchError, atomic_write, prepare_output
from .parts import normalize_manifest
from .rendering import validate_file
from .semantic import SemanticIndex, build_semantic_index
from .syntax import extract_music_variables


_INCLUDE_RE = re.compile(r'\\include\s+"([^"\n]+)"')
_SCIENTIFIC_RE = re.compile(r"^([A-Ga-g])(?:[#b]|is|es)?(-?\d+)$")
_LILYPOND_PITCH_RE = re.compile(r"^([a-g])(?:is|es|isis|eses)?([,']*)$")
_SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2}


# Diatonic pitch positions use C4 == 28, matching semantic.py.  The practical
# range is a review boundary; the absolute range is deliberately conservative.
INSTRUMENT_RANGES: dict[str, dict[str, tuple[int, int]]] = {
    "violin": {"practical": (24, 50), "absolute": (24, 52)},       # G3-D7 / G3-A7
    "viola": {"practical": (21, 46), "absolute": (21, 47)},        # C3-E6 / C3-A6
    "cello": {"practical": (14, 42), "absolute": (14, 44)},        # C2-C6 / C2-E6
    "double-bass": {"practical": (16, 39), "absolute": (14, 42)},  # E2-G5 / C2-C6 written
    "flute": {"practical": (28, 49), "absolute": (27, 51)},        # C4-C7 / B3-E7
    "oboe": {"practical": (27, 47), "absolute": (27, 49)},         # B3-A6 / B3-C7
    "clarinet-bb": {"practical": (23, 49), "absolute": (23, 53)},  # E3-C7 / E3-G7 written
    "bassoon": {"practical": (13, 37), "absolute": (13, 39)},      # B1-E5 / B1-G5
    "trumpet-bb": {"practical": (24, 42), "absolute": (24, 46)},  # F3-C6 / F3-E6 written
    "horn-f": {"practical": (17, 42), "absolute": (13, 45)},      # F2-C6 / B1-D6 written
    "trombone": {"practical": (16, 38), "absolute": (16, 41)},    # E2-F5 / E2-B5
    "piano": {"practical": (5, 56), "absolute": (5, 56)},         # A0-C8
}

_INSTRUMENT_ALIASES = {
    "double bass": "double-bass",
    "double_bass": "double-bass",
    "contrabass": "double-bass",
    "bb clarinet": "clarinet-bb",
    "b-flat clarinet": "clarinet-bb",
    "clarinet": "clarinet-bb",
    "bb trumpet": "trumpet-bb",
    "b-flat trumpet": "trumpet-bb",
    "trumpet": "trumpet-bb",
    "horn in f": "horn-f",
    "f horn": "horn-f",
    "horn": "horn-f",
}


def _scientific_pitch(value: int) -> str:
    octave, note = divmod(value, 7)
    return f"{'CDEFGAB'[note]}{octave}"


def _parse_scientific(value: str) -> int:
    match = _SCIENTIFIC_RE.fullmatch(value.strip())
    if not match:
        raise WorkbenchError(f"Invalid scientific pitch: {value}", "MANIFEST_SCHEMA", exit_code=2)
    return int(match.group(2)) * 7 + "CDEFGAB".index(match.group(1).upper())


def _transpose_shift(config: Any) -> int:
    if not config:
        return 0
    values: list[int] = []
    for key in ("from", "to"):
        match = _LILYPOND_PITCH_RE.fullmatch(str(config[key]).strip())
        if not match:
            raise WorkbenchError(f"Invalid LilyPond transpose pitch: {config[key]}", "MANIFEST_SCHEMA", exit_code=2)
        octave = match.group(2).count("'") - match.group(2).count(",")
        values.append(octave * 7 + "cdefgab".index(match.group(1)))
    return values[1] - values[0]


def _instrument_name(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return _INSTRUMENT_ALIASES.get(normalized, normalized)


def _ranges(part: dict[str, Any]) -> dict[str, tuple[int, int]] | None:
    instrument = _instrument_name(part.get("instrument"))
    defaults = INSTRUMENT_RANGES.get(instrument or "")
    override = part.get("range_override")
    if override is None:
        return defaults
    if not isinstance(override, dict):
        raise WorkbenchError(f"Part {part['id']} range_override must be a mapping", "MANIFEST_SCHEMA", exit_code=2)
    result: dict[str, tuple[int, int]] = dict(defaults or {})
    for boundary in ("practical", "absolute"):
        raw = override.get(boundary)
        if raw is None:
            continue
        if not isinstance(raw, dict) or not isinstance(raw.get("low"), str) or not isinstance(raw.get("high"), str):
            raise WorkbenchError(
                f"Part {part['id']} {boundary} range requires low and high scientific pitches",
                "MANIFEST_SCHEMA",
                exit_code=2,
            )
        result[boundary] = (_parse_scientific(raw["low"]), _parse_scientific(raw["high"]))
    if "practical" not in result or "absolute" not in result:
        raise WorkbenchError(
            f"Part {part['id']} needs both practical and absolute ranges when its instrument is unknown",
            "MANIFEST_SCHEMA",
            exit_code=2,
        )
    practical, absolute = result["practical"], result["absolute"]
    if not (absolute[0] <= practical[0] <= practical[1] <= absolute[1]):
        raise WorkbenchError(f"Part {part['id']} range boundaries are inconsistent", "MANIFEST_SCHEMA", exit_code=2)
    return result


def _diag(rule_id: str, severity: str, message: str, **kwargs: Any) -> Diagnostic:
    details = dict(kwargs.pop("details", {}))
    details["rule_id"] = rule_id
    code = rule_id.upper().replace(".", "_").replace("-", "_")
    return Diagnostic(severity, code, message, details=details, **kwargs)


def _structural_diagnostics(source: Path) -> list[Diagnostic]:
    text = source.read_text(encoding="utf-8")
    diagnostics: list[Diagnostic] = []
    try:
        variables = extract_music_variables(text)
    except WorkbenchError as exc:
        return [_diag("structure.unmatched-delimiter", "error", str(exc), file=str(source))]
    if not variables:
        diagnostics.append(_diag("structure.no-music-variable", "warning", "No top-level music variables were found", file=str(source)))
    seen: dict[str, int] = {}
    for variable in variables:
        if variable.name in seen:
            diagnostics.append(
                _diag(
                    "structure.duplicate-variable",
                    "error",
                    f"Music variable {variable.name} is defined more than once",
                    file=str(source),
                    line=variable.line,
                )
            )
        seen[variable.name] = variable.line
    for match in _INCLUDE_RE.finditer(text):
        included = (source.parent / match.group(1)).resolve()
        if not included.is_file():
            diagnostics.append(
                _diag(
                    "structure.include-not-found",
                    "error",
                    f"Included file does not exist: {match.group(1)}",
                    file=str(source),
                    line=text.count("\n", 0, match.start()) + 1,
                )
            )
    return diagnostics


def _range_diagnostics(index: SemanticIndex, part: dict[str, Any]) -> list[Diagnostic]:
    boundaries = _ranges(part)
    if boundaries is None:
        return [
            _diag(
                "range.unknown-instrument",
                "info",
                f"No built-in range is available for instrument {part.get('instrument')!r}",
                file=index.source,
                details={"part": part["id"], "instrument": part.get("instrument")},
            )
        ]
    shift = _transpose_shift(part.get("transpose")) if part.get("pitch_basis") == "concert" else 0
    practical = boundaries["practical"]
    absolute = boundaries["absolute"]
    candidates: dict[str, tuple[int, Any]] = {}
    for event in index.events:
        if event.grace or event.cue or not event.pitches:
            continue
        for pitch in event.pitches:
            written = pitch + shift
            if written < absolute[0]:
                key = "range.below-absolute"
            elif written > absolute[1]:
                key = "range.above-absolute"
            elif written < practical[0]:
                key = "range.below-practical"
            elif written > practical[1]:
                key = "range.above-practical"
            else:
                continue
            previous = candidates.get(key)
            if previous is None or ("below" in key and written < previous[0]) or ("above" in key and written > previous[0]):
                candidates[key] = (written, event)
    diagnostics: list[Diagnostic] = []
    for rule_id, (pitch, event) in candidates.items():
        severity = "error" if "absolute" in rule_id else "warning"
        position = index.position(event.offset)
        limit = absolute if "absolute" in rule_id else practical
        diagnostics.append(
            _diag(
                rule_id,
                severity,
                f"Part {part['id']} has written pitch {_scientific_pitch(pitch)} outside the "
                f"{('absolute' if 'absolute' in rule_id else 'practical')} range "
                f"{_scientific_pitch(limit[0])}–{_scientific_pitch(limit[1])}",
                file=event.source.file,
                line=event.source.line,
                column=event.source.column,
                details={
                    "part": part["id"],
                    "instrument": _instrument_name(part.get("instrument")),
                    "pitch": _scientific_pitch(pitch),
                    "pitch_basis": part.get("pitch_basis", "concert"),
                    "written_pitch_shift": shift,
                    "measure": position["measure"],
                    "beat": position["beat"],
                    "confidence": 1.0,
                },
            )
        )
    return diagnostics


def _manifest_diagnostics(source: Path, manifest: dict[str, Any]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    source_text = source.read_text(encoding="utf-8")
    try:
        variables = {item.name for item in extract_music_variables(source_text)}
    except WorkbenchError as exc:
        return [_diag("structure.unmatched-delimiter", "error", str(exc), file=str(source))]
    declared_tags = set(re.findall(r"\\tag\s+#?'?([A-Za-z][A-Za-z0-9_-]*)", source_text))
    ids: set[str] = set()
    outputs: set[str] = set()
    for part in manifest["parts"]:
        part_id = str(part["id"])
        output_name = str(part.get("output_name", part_id))
        if part_id in ids:
            diagnostics.append(_diag("parts.duplicate-id", "error", f"Duplicate part id: {part_id}", file=str(source), details={"part": part_id}))
        ids.add(part_id)
        if output_name in outputs:
            diagnostics.append(_diag("parts.duplicate-output", "error", f"Duplicate part output name: {output_name}", file=str(source), details={"part": part_id}))
        outputs.add(output_name)
        for tag in part.get("tags", []):
            if tag not in declared_tags:
                diagnostics.append(
                    _diag(
                        "parts.tag-not-found",
                        "error",
                        f"Part {part_id} selects undeclared tag {tag}",
                        file=str(source),
                        details={"part": part_id, "tag": tag},
                    )
                )
        if part["variable"] not in variables:
            diagnostics.append(
                _diag(
                    "parts.variable-not-found",
                    "error",
                    f"Part {part_id} references missing variable {part['variable']}",
                    file=str(source),
                    details={"part": part_id},
                )
            )
            continue
        try:
            index = build_semantic_index(source, str(part["variable"]))
            for raw_diagnostic in index.diagnostics:
                diagnostic = replace(raw_diagnostic, details=dict(raw_diagnostic.details))
                diagnostic.details.setdefault("rule_id", f"semantic.{diagnostic.code.lower().replace('_', '-')}")
                diagnostic.details.setdefault("part", part_id)
                diagnostics.append(diagnostic)
            diagnostics.extend(_range_diagnostics(index, part))
            instrument = _instrument_name(part.get("instrument"))
            if instrument in {"violin", "viola", "cello"}:
                initial_clef = part.get("clef", {}).get("initial") if isinstance(part.get("clef"), dict) else None
                analysis = analyze_clef_index(index, instrument, initial_clef=initial_clef)
                for raw_diagnostic in analysis.diagnostics[len(index.diagnostics) :]:
                    diagnostic = replace(raw_diagnostic, details=dict(raw_diagnostic.details))
                    diagnostic.details.setdefault("rule_id", f"clef.{diagnostic.code.lower().replace('_', '-')}")
                    diagnostic.details.setdefault("part", part_id)
                    diagnostics.append(diagnostic)
        except WorkbenchError as exc:
            diagnostics.append(_diag("semantic.index-failed", "error", str(exc), file=str(source), details={"part": part_id}))
    return diagnostics


def _apply_suppressions(diagnostics: list[Diagnostic], suppressions: list[dict[str, Any]]) -> None:
    matched: set[int] = set()
    for diagnostic in diagnostics:
        rule_id = str(diagnostic.details.get("rule_id", diagnostic.code.lower()))
        part = diagnostic.details.get("part")
        for index, suppression in enumerate(suppressions):
            if suppression["rule_id"] != rule_id:
                continue
            if suppression.get("part") is not None and suppression.get("part") != part:
                continue
            diagnostic.details.update(
                {"suppressed": True, "suppression_reason": suppression["reason"], "original_severity": diagnostic.severity}
            )
            matched.add(index)
            break
    for index, suppression in enumerate(suppressions):
        if index not in matched:
            diagnostics.append(
                _diag(
                    "lint.unused-suppression",
                    "warning",
                    f"Suppression did not match any finding: {suppression['rule_id']}",
                    details={"suppressed_rule_id": suppression["rule_id"], "part": suppression.get("part")},
                )
            )


def _report_item(diagnostic: Diagnostic) -> dict[str, Any]:
    details = dict(diagnostic.details)
    rule_id = str(details.pop("rule_id", diagnostic.code.lower()))
    suppressed = bool(details.pop("suppressed", False))
    return {
        "rule_id": rule_id,
        "severity": diagnostic.severity,
        "message": diagnostic.message,
        "location": {"file": diagnostic.file, "line": diagnostic.line, "column": diagnostic.column},
        "measure": details.pop("measure", None),
        "beat": details.pop("beat", None),
        "confidence": details.pop("confidence", 1.0),
        "pitch_basis": details.pop("pitch_basis", None),
        "suppressed": suppressed,
        "suppression_reason": details.pop("suppression_reason", None),
        "details": details,
    }


def lint_score(
    source: Path,
    *,
    manifest_path: Path | None = None,
    output_path: Path | None = None,
    fail_on: str = "error",
    static_only: bool = False,
    force: bool = False,
    timeout: int = 60,
) -> Result:
    if fail_on not in _SEVERITY_ORDER:
        raise WorkbenchError(f"Invalid fail-on severity: {fail_on}", "INVALID_ARGUMENT", exit_code=2)
    source = source.resolve()
    diagnostics = _structural_diagnostics(source)
    validated = validate_file(source, timeout=timeout, static_only=static_only)
    for diagnostic in validated.diagnostics:
        diagnostic.details.setdefault("rule_id", f"compiler.{diagnostic.code.lower().replace('_', '-')}")
    diagnostics.extend(validated.diagnostics)
    manifest: dict[str, Any] | None = None
    suppressions: list[dict[str, Any]] = []
    inputs = [str(source)]
    if manifest_path is not None:
        manifest_file = manifest_path.resolve()
        inputs.append(str(manifest_file))
        raw = yaml.safe_load(manifest_file.read_text(encoding="utf-8"))
        manifest = normalize_manifest(raw)
        declared_source = (manifest_file.parent / manifest["source"]).resolve()
        if declared_source != source:
            diagnostics.append(
                _diag(
                    "parts.source-mismatch",
                    "error",
                    f"Manifest source resolves to {declared_source}, not {source}",
                    file=str(manifest_file),
                )
            )
        else:
            diagnostics.extend(_manifest_diagnostics(source, manifest))
        suppressions = manifest.get("suppressions", [])
    _apply_suppressions(diagnostics, suppressions)
    items = [_report_item(item) for item in diagnostics]
    threshold = _SEVERITY_ORDER[fail_on]
    failed = any(not item["suppressed"] and _SEVERITY_ORDER[item["severity"]] >= threshold for item in items)
    report = {
        "schema_version": 1,
        "source": str(source),
        "manifest": str(manifest_path.resolve()) if manifest_path else None,
        "fail_on": fail_on,
        "static_only": static_only,
        "summary": {
            "errors": sum(item["severity"] == "error" and not item["suppressed"] for item in items),
            "warnings": sum(item["severity"] == "warning" and not item["suppressed"] for item in items),
            "info": sum(item["severity"] == "info" and not item["suppressed"] for item in items),
            "suppressed": sum(item["suppressed"] for item in items),
        },
        "findings": items,
    }
    artifacts: list[str] = []
    if output_path is not None:
        destination = prepare_output(output_path, force=force)
        atomic_write(destination, json.dumps(report, ensure_ascii=False, indent=2) + "\n", force=True)
        artifacts.append(str(destination))
    return Result(
        not failed,
        "lint",
        inputs,
        artifacts,
        diagnostics,
        {"report": report},
    )
