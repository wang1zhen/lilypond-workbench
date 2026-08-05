from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from .clefs import analyze_clefs
from .common import Diagnostic, Result, SKILL_ROOT, WorkbenchError, ensure_input, prepare_output, print_result
from .diagnostics import parse_lilypond_log
from .documents import build_document
from .harmony import analyze_harmony
from .importers import clean_file, import_score
from .parts import extract_parts, write_manifest
from .rendering import batch_render, doctor, render_file, validate_file


def _add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Emit structured JSON")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lilypond-workbench", description="Deterministic tools for the LilyPond Workbench skill")
    parser.add_argument("--version", action="version", version="lilypond-workbench 0.1.0")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor_parser = sub.add_parser("doctor", help="Check required local tools and versions")
    _add_json(doctor_parser)

    new_parser = sub.add_parser("new", help="Create a score from a bundled template")
    new_parser.add_argument("template", help="Template name, such as piano or lead-sheet")
    new_parser.add_argument("output", type=Path)
    new_parser.add_argument("--force", action="store_true")
    _add_json(new_parser)

    render = sub.add_parser("render", help="Compile one LilyPond score")
    render.add_argument("input", type=Path)
    render.add_argument("--output-dir", type=Path)
    render.add_argument("--format", choices=["pdf", "png", "svg", "ps"], default="pdf")
    render.add_argument("--resolution", type=int)
    render.add_argument("--backend", choices=["svg", "ps", "eps", "cairo"])
    render.add_argument("--no-point-and-click", action="store_true")
    render.add_argument("--preview", action="store_true")
    render.add_argument("--timeout", type=int, default=60)
    _add_json(render)

    batch = sub.add_parser("batch-render", help="Compile several LilyPond scores")
    batch.add_argument("paths", nargs="+", type=Path)
    batch.add_argument("--output-dir", type=Path, required=True)
    batch.add_argument("--pattern", default="*.ly")
    batch.add_argument("--recursive", action="store_true")
    batch.add_argument("--jobs", type=int, default=1)
    batch.add_argument("--continue-on-error", action="store_true")
    batch.add_argument("--format", choices=["pdf", "png", "svg", "ps"], default="pdf")
    batch.add_argument("--resolution", type=int)
    batch.add_argument("--backend", choices=["svg", "ps", "eps", "cairo"])
    batch.add_argument("--no-point-and-click", action="store_true")
    batch.add_argument("--preview", action="store_true")
    batch.add_argument("--timeout", type=int, default=60)
    _add_json(batch)

    validate = sub.add_parser("validate", help="Check durations and run LilyPond without emitting pages")
    validate.add_argument("input", type=Path)
    validate.add_argument("--static-only", action="store_true")
    validate.add_argument("--timeout", type=int, default=60)
    _add_json(validate)

    log = sub.add_parser("parse-log", help="Parse LilyPond output into diagnostics")
    log.add_argument("log", nargs="?", type=Path)
    log.add_argument("--text")
    _add_json(log)

    importer = sub.add_parser("import-score", help="Convert MusicXML, MIDI, or ABC to LilyPond")
    importer.add_argument("input", type=Path)
    importer.add_argument("--output", type=Path)
    importer.add_argument("--preserve-layout", action="store_true")
    importer.add_argument("--preserve-beams", action="store_true")
    importer.add_argument("--force", action="store_true")
    importer.add_argument("--timeout", type=int, default=120)
    _add_json(importer)

    clean = sub.add_parser("clean", help="Normalize LilyPond version and formatting")
    clean.add_argument("input", type=Path)
    clean.add_argument("--output", type=Path)
    clean.add_argument("--in-place", action="store_true")
    clean.add_argument("--force", action="store_true")
    _add_json(clean)

    manifest = sub.add_parser("parts-manifest", help="Generate a versioned parts manifest")
    manifest.add_argument("source", type=Path)
    manifest.add_argument("--output", type=Path, required=True)
    manifest.add_argument("--format", choices=["yaml", "json"], default="yaml")
    manifest.add_argument("--force", action="store_true")
    _add_json(manifest)

    parts = sub.add_parser("extract-parts", help="Generate independent part wrappers")
    parts.add_argument("manifest", type=Path)
    parts.add_argument("--output-dir", type=Path)
    parts.add_argument("--compile", action="store_true", dest="compile_parts")
    parts.add_argument("--force", action="store_true")
    parts.add_argument("--timeout", type=int, default=60)
    _add_json(parts)

    harmony = sub.add_parser("analyze-harmony", help="Infer chord symbols, local keys, and Roman numerals")
    harmony.add_argument("input", type=Path)
    harmony.add_argument("--output", type=Path, required=True)
    harmony.add_argument("--report", type=Path)
    harmony.add_argument("--score-index", type=int, default=0)
    harmony.add_argument("--key", dest="key_override")
    harmony.add_argument("--window", type=int, default=4)
    harmony.add_argument("--max-chords", type=int, default=3)
    harmony.add_argument("--trim-below", type=float, default=0.25)
    harmony.add_argument("--confidence-threshold", type=float, default=0.60)
    harmony.add_argument("--force", action="store_true")
    harmony.add_argument("--timeout", type=int, default=120)
    _add_json(harmony)

    clefs = sub.add_parser("analyze-clefs", help="Recommend clef changes for a string part")
    clefs.add_argument("input", type=Path)
    clefs.add_argument("--instrument", choices=["violin", "viola", "cello"], required=True)
    clefs.add_argument("--variable", required=True, help="Music variable to analyze")
    clefs.add_argument("--initial-clef", choices=["treble", "alto", "tenor", "bass"])
    clefs.add_argument("--output", type=Path, required=True)
    clefs.add_argument("--force", action="store_true")
    _add_json(clefs)

    document = sub.add_parser("build-document", help="Build a LilyPond-enabled LaTeX document")
    document.add_argument("input", type=Path)
    document.add_argument("--output-dir", type=Path, required=True)
    document.add_argument("--timeout", type=int, default=180)
    _add_json(document)
    return parser


def _new_score(args: argparse.Namespace) -> Result:
    template = args.template[:-3] if args.template.endswith(".ly") else args.template
    source = SKILL_ROOT / "assets" / "templates" / f"{template}.ly"
    if not source.is_file():
        available = sorted(path.stem for path in (SKILL_ROOT / "assets" / "templates").glob("*.ly"))
        raise WorkbenchError(f"Unknown template {args.template}; available: {', '.join(available)}", "TEMPLATE_NOT_FOUND", exit_code=2)
    destination = prepare_output(args.output, force=args.force)
    shutil.copyfile(source, destination)
    return Result(True, "new", [str(source)], [str(destination)])


def dispatch(args: argparse.Namespace) -> Result:
    if args.command == "doctor":
        return doctor()
    if args.command == "new":
        return _new_score(args)
    if args.command == "render":
        source = ensure_input(args.input, {".ly"})
        return render_file(
            source,
            output_dir=args.output_dir,
            fmt=args.format,
            resolution=args.resolution,
            backend=args.backend,
            no_point_and_click=args.no_point_and_click,
            preview=args.preview,
            timeout=args.timeout,
        )
    if args.command == "batch-render":
        return batch_render(
            args.paths,
            output_dir=args.output_dir,
            pattern=args.pattern,
            recursive=args.recursive,
            jobs=max(1, args.jobs),
            continue_on_error=args.continue_on_error,
            fmt=args.format,
            resolution=args.resolution,
            backend=args.backend,
            no_point_and_click=args.no_point_and_click,
            preview=args.preview,
            timeout=args.timeout,
        )
    if args.command == "validate":
        return validate_file(ensure_input(args.input, {".ly"}), timeout=args.timeout, static_only=args.static_only)
    if args.command == "parse-log":
        if args.text is not None:
            text = args.text
            inputs: list[str] = []
        elif args.log:
            source = ensure_input(args.log)
            text = source.read_text(encoding="utf-8")
            inputs = [str(source)]
        else:
            text = sys.stdin.read()
            inputs = ["stdin"]
        diagnostics = parse_lilypond_log(text)
        return Result(not any(item.severity == "error" for item in diagnostics), "parse-log", inputs, diagnostics=diagnostics)
    if args.command == "import-score":
        return import_score(
            ensure_input(args.input),
            output_path=args.output,
            force=args.force,
            preserve_layout=args.preserve_layout,
            preserve_beams=args.preserve_beams,
            timeout=args.timeout,
        )
    if args.command == "clean":
        return clean_file(
            ensure_input(args.input, {".ly", ".ily"}),
            output_path=args.output,
            in_place=args.in_place,
            force=args.force,
        )
    if args.command == "parts-manifest":
        return write_manifest(
            ensure_input(args.source, {".ly", ".ily"}),
            args.output,
            force=args.force,
            as_json=args.format == "json",
        )
    if args.command == "extract-parts":
        return extract_parts(
            ensure_input(args.manifest, {".yaml", ".yml", ".json"}),
            output_dir=args.output_dir,
            compile_parts=args.compile_parts,
            force=args.force,
            timeout=args.timeout,
        )
    if args.command == "analyze-harmony":
        return analyze_harmony(
            ensure_input(args.input),
            output_path=args.output,
            report_path=args.report,
            score_index=args.score_index,
            key_override=args.key_override,
            window=args.window,
            max_chords=args.max_chords,
            trim_below=args.trim_below,
            confidence_threshold=args.confidence_threshold,
            force=args.force,
            timeout=args.timeout,
        )
    if args.command == "analyze-clefs":
        return analyze_clefs(
            ensure_input(args.input, {".ly", ".ily"}),
            variable=args.variable,
            instrument=args.instrument,
            output_path=args.output,
            initial_clef=args.initial_clef,
            force=args.force,
        )
    if args.command == "build-document":
        return build_document(ensure_input(args.input, {".lytex", ".tex"}), output_dir=args.output_dir, timeout=args.timeout)
    raise WorkbenchError(f"Unknown command: {args.command}", "INVALID_ARGUMENT", exit_code=2)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = dispatch(args)
        print_result(result, as_json=args.json)
        return 0 if result.ok else 1
    except WorkbenchError as exc:
        result = Result(False, args.command or "workbench", diagnostics=[Diagnostic("error", exc.code, str(exc))])
        print_result(result, as_json=getattr(args, "json", False))
        return exc.exit_code
    except KeyboardInterrupt:
        result = Result(False, args.command or "workbench", diagnostics=[Diagnostic("error", "INTERRUPTED", "Operation interrupted")])
        print_result(result, as_json=getattr(args, "json", False))
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
