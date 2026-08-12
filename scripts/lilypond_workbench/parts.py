from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from .clefs import ClefAnalysis, analyze_clef_index, clef_track_name, render_clef_track
from .common import Diagnostic, Result, WorkbenchError, atomic_write, prepare_output
from .rendering import render_file
from .semantic import SemanticIndex, build_semantic_index
from .syntax import extract_music_variables, masked_source, rewrite_relative_includes, sanitize_definitions


STAFF_RE = re.compile(
    r"\\new\s+(?P<staff>Staff|DrumStaff|RhythmicStaff|TabStaff)"
    r"(?P<settings>\s*\\with\s*\{.*?\})?\s*"
    r"(?:\\(?P<variable>[A-Za-z][A-Za-z0-9_-]*)|\{)",
    re.DOTALL,
)
INSTRUMENT_RE = re.compile(r'instrumentName\s*=\s*"([^"]+)"')


def _part_id(name: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", re.sub(r"Music$", "", name))
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "part"


def _guess_instrument(name: str) -> str | None:
    lower = name.lower()
    if "violin" in lower:
        return "violin"
    if "viola" in lower:
        return "viola"
    if "cello" in lower or "violoncello" in lower:
        return "cello"
    return None


def _guess_clef(name: str, instrument: str | None = None) -> str:
    lower = name.lower()
    if instrument == "viola" or "alto" in lower:
        return "alto"
    if instrument == "cello" or any(item in lower for item in ("bass", "bassoon", "tuba", "trombone")):
        return "bass"
    if "drum" in lower or "percussion" in lower:
        return "percussion"
    return "treble"


def build_manifest(source: Path) -> tuple[dict[str, Any], list[Diagnostic]]:
    text = source.read_text(encoding="utf-8")
    variables = extract_music_variables(text)
    variable_names = {item.name for item in variables}
    mappings: dict[str, dict[str, str]] = {}
    masked = masked_source(text)
    for match in STAFF_RE.finditer(masked):
        variable = match.group("variable")
        if not variable or variable not in variable_names:
            continue
        original_settings = text[match.start("settings") : match.end("settings")]
        instrument_match = INSTRUMENT_RE.search(original_settings)
        mappings[variable] = {
            "staff_type": match.group("staff"),
            "name": instrument_match.group(1) if instrument_match else "",
        }
    diagnostics: list[Diagnostic] = []
    parts: list[dict[str, Any]] = []
    ignored = {"global", "chordNames", "harmonies", "lyrics", "verse", "paper", "layout"}
    for variable in variables:
        if variable.name in ignored or variable.name.lower().endswith(("lyrics", "chords")):
            continue
        mapping = mappings.get(variable.name, {})
        name = mapping.get("name") or re.sub(r"(?<!^)([A-Z])", r" \1", re.sub(r"Music$", "", variable.name)).title()
        instrument = _guess_instrument(name)
        item = {
            "id": _part_id(variable.name),
            "name": name,
            "variable": variable.name,
            "staff_type": mapping.get("staff_type", "Staff"),
            "instrument": instrument,
            "pitch_basis": "concert",
            "clef": {
                "initial": _guess_clef(name, instrument),
                "policy": "suggest" if instrument in {"violin", "viola", "cello"} else "preserve",
            },
        }
        if not mapping:
            item["needs_review"] = True
            diagnostics.append(
                Diagnostic(
                    "warning",
                    "PART_MAPPING_REVIEW",
                    f"Could not map {variable.name} to a Staff declaration; review the generated manifest",
                    file=str(source),
                    line=variable.line,
                )
            )
        parts.append(item)
    manifest = {
        "schema_version": 3,
        "source": source.name,
        "source_mode": "strip-score-blocks",
        "output_dir": "build/parts",
        "parts": parts,
    }
    return manifest, diagnostics


def write_manifest(source: Path, output: Path, *, force: bool = False, as_json: bool = False) -> Result:
    manifest, diagnostics = build_manifest(source)
    text = json.dumps(manifest, ensure_ascii=False, indent=2) if as_json else yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True)
    atomic_write(prepare_output(output, force=force), text, force=True)
    return Result(True, "parts-manifest", [str(source)], [str(output.resolve())], diagnostics, {"parts": len(manifest["parts"])})


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _clef_config(part: dict[str, Any]) -> dict[str, str]:
    raw = part.get("clef")
    if isinstance(raw, str):
        return {"initial": raw, "policy": "preserve"}
    if not isinstance(raw, dict):
        return {"initial": _guess_clef(str(part.get("name", "")), part.get("instrument")), "policy": "preserve"}
    return {
        "initial": str(raw.get("initial") or _guess_clef(str(part.get("name", "")), part.get("instrument"))),
        "policy": str(raw.get("policy", "preserve")),
    }


def normalize_manifest(manifest: Any) -> dict[str, Any]:
    if not isinstance(manifest, dict) or manifest.get("schema_version") not in {1, 2, 3}:
        raise WorkbenchError("Parts manifest must use schema_version: 1, 2, or 3", "MANIFEST_SCHEMA", exit_code=2)
    normalized = dict(manifest)
    parts = manifest.get("parts")
    if not isinstance(parts, list):
        raise WorkbenchError("Parts manifest must contain a parts list", "MANIFEST_SCHEMA", exit_code=2)
    normalized_parts: list[dict[str, Any]] = []
    for raw_part in parts:
        if not isinstance(raw_part, dict) or not all(key in raw_part for key in ("id", "name", "variable")):
            raise WorkbenchError("Each part requires id, name, and variable", "MANIFEST_SCHEMA", exit_code=2)
        part = dict(raw_part)
        instrument = part.get("instrument") or _guess_instrument(str(part["name"]))
        part["instrument"] = instrument
        if manifest["schema_version"] == 1:
            part["clef"] = {"initial": str(part.get("clef") or _guess_clef(str(part["name"]), instrument)), "policy": "preserve"}
        else:
            config = _clef_config(part)
            if config["policy"] not in {"preserve", "suggest", "auto"}:
                raise WorkbenchError(
                    f"Part {part['id']} has invalid clef policy: {config['policy']}",
                    "MANIFEST_SCHEMA",
                    exit_code=2,
                )
            if config["policy"] != "preserve" and instrument not in {"violin", "viola", "cello"}:
                raise WorkbenchError(
                    f"Part {part['id']} requires instrument violin, viola, or cello for clef policy {config['policy']}",
                    "MANIFEST_SCHEMA",
                    exit_code=2,
                )
            part["clef"] = config
        if manifest["schema_version"] == 3 and "pitch_basis" not in part:
            raise WorkbenchError(f"Part {part['id']} requires pitch_basis in schema v3", "MANIFEST_SCHEMA", exit_code=2)
        pitch_basis = str(part.get("pitch_basis", "concert"))
        if pitch_basis not in {"concert", "written"}:
            raise WorkbenchError(
                f"Part {part['id']} has invalid pitch_basis: {pitch_basis}",
                "MANIFEST_SCHEMA",
                exit_code=2,
            )
        part["pitch_basis"] = pitch_basis
        transpose = part.get("transpose")
        if transpose is not None and (
            not isinstance(transpose, dict)
            or not isinstance(transpose.get("from"), str)
            or not isinstance(transpose.get("to"), str)
        ):
            raise WorkbenchError(
                f"Part {part['id']} transpose requires string from and to pitches",
                "MANIFEST_SCHEMA",
                exit_code=2,
            )
        tags = part.get("tags")
        if tags is not None and (not isinstance(tags, list) or not all(isinstance(tag, str) and tag for tag in tags)):
            raise WorkbenchError(f"Part {part['id']} tags must be a list of strings", "MANIFEST_SCHEMA", exit_code=2)
        range_override = part.get("range_override")
        if range_override is not None and not isinstance(range_override, dict):
            raise WorkbenchError(f"Part {part['id']} range_override must be a mapping", "MANIFEST_SCHEMA", exit_code=2)
        normalized_parts.append(part)
    normalized["parts"] = normalized_parts
    suppressions = manifest.get("suppressions", [])
    if not isinstance(suppressions, list):
        raise WorkbenchError("Manifest suppressions must be a list", "MANIFEST_SCHEMA", exit_code=2)
    for item in suppressions:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("rule_id"), str)
            or not isinstance(item.get("reason"), str)
            or not item["reason"].strip()
        ):
            raise WorkbenchError("Each suppression requires rule_id and a non-empty reason", "MANIFEST_SCHEMA", exit_code=2)
    normalized["suppressions"] = suppressions
    normalized["schema_version"] = 3
    return normalized


# Backward-compatible private alias for callers written against 0.1.
_normalize_manifest = normalize_manifest


def _wrapper(
    shared: Path,
    part: dict[str, Any],
    *,
    clef_track: str | None = None,
    clef_track_variable: str | None = None,
) -> str:
    transpose = part.get("transpose") or {}
    music = f"\\{part['variable']}"
    if transpose:
        music = f"\\transpose {transpose['from']} {transpose['to']} {{ {music} }}"
    if part.get("tags"):
        tags = " ".join(part["tags"])
        music = f"\\keepWithTag #'({tags}) {{ {music} }}"
    if clef_track_variable:
        music = f"<< {{ {music} }} {{ \\{clef_track_variable} }} >>"
    lines = [
        '\\version "2.24.4"',
        f'\\include "{shared.as_posix()}"',
        "",
    ]
    if clef_track:
        lines.extend([clef_track.rstrip(), ""])
    lines.extend([
        "\\book {",
        f'  \\bookOutputName "{_escape(part.get("output_name", part["id"]))}"',
        f'  \\header {{ instrument = "{_escape(part["name"])}" }}',
        "  \\score {",
        f'    \\new {part.get("staff_type", "Staff")} \\with {{',
        f'      instrumentName = "{_escape(part["name"])}"',
        f'      shortInstrumentName = "{_escape(part.get("short_name", part["name"]))}"',
        "    } {",
    ])
    config = _clef_config(part)
    if not clef_track_variable and config["initial"]:
        lines.append(f"      \\clef {config['initial']}")
    lines.extend([f"      {music}", "    }", "    \\layout { }", "    \\midi { }", "  }", "}", ""])
    return "\n".join(lines)


def extract_parts(
    manifest_path: Path,
    *,
    output_dir: Path | None = None,
    compile_parts: bool = False,
    force: bool = False,
    timeout: int = 60,
) -> Result:
    manifest_file = manifest_path.resolve()
    raw_manifest = yaml.safe_load(manifest_file.read_text(encoding="utf-8"))
    original_schema = raw_manifest.get("schema_version") if isinstance(raw_manifest, dict) else None
    manifest = normalize_manifest(raw_manifest)
    source = (manifest_file.parent / manifest["source"]).resolve()
    if not source.is_file():
        raise WorkbenchError(f"Manifest source not found: {source}", "INPUT_NOT_FOUND", exit_code=2)
    destination = (output_dir or manifest_file.parent / manifest.get("output_dir", "build/parts")).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    original = source.read_text(encoding="utf-8")
    shared_text = rewrite_relative_includes(sanitize_definitions(original), source.parent)
    remaining = {item.name for item in extract_music_variables(shared_text)}
    required = {part["variable"] for part in manifest.get("parts", [])}
    missing = sorted(required - remaining)
    if missing:
        raise WorkbenchError(
            f"Part variables are not available outside score/book blocks: {', '.join(missing)}",
            "PARTS_UNSUPPORTED_STRUCTURE",
        )
    shared = destination / "_shared.ily"
    wrappers = [destination / f"{part['id']}.ly" for part in manifest.get("parts", [])]
    reports = [
        destination / f"{part['id']}.clefs.json"
        for part in manifest.get("parts", [])
        if _clef_config(part)["policy"] in {"suggest", "auto"}
    ]
    if not force:
        existing = [path for path in [shared, *wrappers, *reports] if path.exists()]
        if existing:
            raise WorkbenchError(
                f"Generated part output already exists: {existing[0]}; pass --force to replace all generated sources",
                "OUTPUT_EXISTS",
                exit_code=2,
            )
    atomic_write(shared, shared_text, force=force)
    artifacts = [str(shared)]
    diagnostics: list[Diagnostic] = []
    ok = True
    for part, wrapper in zip(manifest.get("parts", []), wrappers, strict=True):
        if part.get("needs_review"):
            diagnostics.append(Diagnostic("warning", "PART_MAPPING_REVIEW", f"Part {part['id']} is marked needs_review"))
        config = _clef_config(part)
        analysis: ClefAnalysis | None = None
        semantic_index: SemanticIndex | None = None
        track_text: str | None = None
        track_variable: str | None = None
        if config["policy"] in {"suggest", "auto"}:
            semantic_index = build_semantic_index(source, str(part["variable"]))
            analysis = analyze_clef_index(
                semantic_index,
                str(part["instrument"]),
                initial_clef=config["initial"],
            )
            diagnostics.extend(analysis.diagnostics)
            report = destination / f"{part['id']}.clefs.json"
            atomic_write(report, json.dumps(analysis.to_dict(semantic_index), ensure_ascii=False, indent=2) + "\n", force=force)
            artifacts.append(str(report))
            if config["policy"] == "auto":
                track_variable = clef_track_name(str(part["id"]))
                track_text = render_clef_track(track_variable, analysis)
        atomic_write(
            wrapper,
            _wrapper(shared, part, clef_track=track_text, clef_track_variable=track_variable),
            force=force,
        )
        artifacts.append(str(wrapper))
        if compile_parts:
            rendered = render_file(wrapper, output_dir=destination, timeout=timeout)
            ok = ok and rendered.ok
            artifacts.extend(rendered.artifacts)
            diagnostics.extend(rendered.diagnostics)
    return Result(
        ok,
        "extract-parts",
        [str(manifest_file), str(source)],
        sorted(set(artifacts)),
        diagnostics,
        {"parts": len(manifest.get("parts", [])), "manifest_schema": original_schema},
    )
