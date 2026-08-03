from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from .common import Diagnostic, Result, WorkbenchError, atomic_write, prepare_output
from .rendering import render_file
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


def _guess_clef(name: str) -> str:
    lower = name.lower()
    if any(item in lower for item in ("viola", "alto")):
        return "alto"
    if any(item in lower for item in ("cello", "bass", "bassoon", "tuba", "trombone")):
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
        item = {
            "id": _part_id(variable.name),
            "name": name,
            "variable": variable.name,
            "staff_type": mapping.get("staff_type", "Staff"),
            "clef": _guess_clef(name),
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
        "schema_version": 1,
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


def _wrapper(shared: Path, part: dict[str, Any]) -> str:
    transpose = part.get("transpose") or {}
    music = f"\\{part['variable']}"
    if transpose:
        music = f"\\transpose {transpose['from']} {transpose['to']} {{ {music} }}"
    lines = [
        '\\version "2.24.4"',
        f'\\include "{shared.as_posix()}"',
        "",
        "\\book {",
        f'  \\bookOutputName "{_escape(part.get("output_name", part["id"]))}"',
        f'  \\header {{ instrument = "{_escape(part["name"])}" }}',
        "  \\score {",
        f'    \\new {part.get("staff_type", "Staff")} \\with {{',
        f'      instrumentName = "{_escape(part["name"])}"',
        f'      shortInstrumentName = "{_escape(part.get("short_name", part["name"]))}"',
        "    } {",
    ]
    if part.get("clef"):
        lines.append(f"      \\clef {part['clef']}")
    if part.get("tags"):
        tags = " ".join(part["tags"])
        music = f"\\keepWithTag #'({tags}) {{ {music} }}"
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
    manifest = yaml.safe_load(manifest_file.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise WorkbenchError("Parts manifest must use schema_version: 1", "MANIFEST_SCHEMA", exit_code=2)
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
    if not force:
        existing = [path for path in [shared, *wrappers] if path.exists()]
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
        atomic_write(wrapper, _wrapper(shared, part), force=force)
        artifacts.append(str(wrapper))
        if compile_parts:
            rendered = render_file(wrapper, output_dir=destination, timeout=timeout)
            ok = ok and rendered.ok
            artifacts.extend(rendered.artifacts)
            diagnostics.extend(rendered.diagnostics)
    return Result(ok, "extract-parts", [str(manifest_file), str(source)], sorted(set(artifacts)), diagnostics, {"parts": len(manifest.get("parts", []))})
