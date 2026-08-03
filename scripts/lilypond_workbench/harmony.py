from __future__ import annotations

import json
import tempfile
from fractions import Fraction
from pathlib import Path
from typing import Any

from music21 import analysis, chord, converter, harmony, key, roman, stream

from .common import Diagnostic, Result, WorkbenchError, atomic_write, run_process
from .diagnostics import parse_lilypond_log
from .syntax import insert_midi_block


def _fraction(value: Any) -> Fraction:
    return Fraction(value).limit_denominator(1024)


def _duration_suffix(quarter_length: Any) -> str:
    whole = _fraction(quarter_length) / 4
    common = {
        Fraction(1): "1",
        Fraction(3, 4): "2.",
        Fraction(1, 2): "2",
        Fraction(3, 8): "4.",
        Fraction(1, 4): "4",
        Fraction(3, 16): "8.",
        Fraction(1, 8): "8",
        Fraction(1, 16): "16",
        Fraction(1, 32): "32",
    }
    if whole in common:
        return common[whole]
    return f"1*{whole.numerator}/{whole.denominator}"


def _pitch_name(name: str) -> str:
    if not name:
        return "c"
    letter = name[0].lower()
    accidental = name[1:]
    accidental = accidental.replace("##", "isis").replace("--", "eses").replace("#", "is").replace("-", "es")
    return letter + accidental


def _chord_token(item: chord.Chord, duration: str) -> str:
    root = item.root()
    bass = item.bass()
    common = item.commonName
    suffixes = {
        "major triad": "",
        "minor triad": ":m",
        "dominant seventh chord": ":7",
        "major seventh chord": ":maj7",
        "minor seventh chord": ":m7",
        "diminished triad": ":dim",
        "diminished seventh chord": ":dim7",
        "half-diminished seventh chord": ":m7.5-",
        "augmented triad": ":aug",
    }
    if root is not None and common in suffixes:
        token = _pitch_name(root.name) + duration + suffixes[common]
        if bass is not None and bass.pitchClass != root.pitchClass:
            token += f"/{_pitch_name(bass.name)}"
        return token
    pitches = " ".join(_pitch_name(pitch.name) for pitch in item.pitches)
    return f"<{pitches}>{duration}"


def _confidence(item: chord.Chord, figure: str) -> tuple[float, str | None]:
    pitch_classes = len(set(item.pitchClasses))
    if not figure or "cannot" in figure.lower() or pitch_classes < 2:
        return 0.3, "Chord symbol could not be identified reliably"
    if pitch_classes >= 3 and item.commonName not in {"forte class", "enharmonic equivalent to major triad"}:
        return (0.92 if item.isConsonant() else 0.78), None
    return 0.58, "Only two distinct pitch classes were available"


def _midi_from_lilypond(source: Path, score_index: int, timeout: int) -> tuple[Path, tempfile.TemporaryDirectory[str], list[Diagnostic]]:
    text = source.read_text(encoding="utf-8")
    analysis_text = insert_midi_block(text, score_index)
    temp_output = tempfile.TemporaryDirectory(prefix="lilypond-workbench-harmony-")
    temporary_source: Path | None = None
    try:
        if analysis_text == text:
            input_file = source
        else:
            handle = tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                suffix=".analysis.ly",
                prefix=".lilypond-workbench-",
                dir=source.parent,
                delete=False,
            )
            handle.write(analysis_text)
            handle.close()
            temporary_source = Path(handle.name)
            input_file = temporary_source
        output_base = Path(temp_output.name) / "analysis"
        process = run_process(
            ["lilypond", "-dno-print-pages", "-o", str(output_base), str(input_file)],
            cwd=source.parent,
            timeout=timeout,
        )
        diagnostics = parse_lilypond_log(process.stderr + "\n" + process.stdout)
        if process.returncode != 0:
            temp_output.cleanup()
            raise WorkbenchError("Could not create MIDI for harmonic analysis", "HARMONY_MIDI_FAILED")
        midi_files = sorted(Path(temp_output.name).glob("*.mid*"))
        if not midi_files:
            temp_output.cleanup()
            raise WorkbenchError("LilyPond produced no MIDI for the selected score", "HARMONY_MIDI_MISSING")
        return midi_files[0], temp_output, diagnostics
    finally:
        if temporary_source is not None:
            temporary_source.unlink(missing_ok=True)


def _measure_keys(score: stream.Stream, window: int, override: str | None) -> list[key.Key]:
    measures = list(score.recurse().getElementsByClass(stream.Measure))
    if override:
        return [key.Key(override)] * max(1, len(measures))
    try:
        analyzer = analysis.floatingKey.KeyAnalyzer(score)
        analyzer.windowSize = window
        keys = analyzer.run()
        if keys:
            return keys
    except Exception:
        pass
    try:
        global_key = score.analyze("key")
    except Exception:
        global_key = key.Key("C")
    return [global_key] * max(1, len(measures))


def analyze_harmony(
    input_path: Path,
    *,
    output_path: Path,
    report_path: Path | None = None,
    score_index: int = 0,
    key_override: str | None = None,
    window: int = 4,
    max_chords: int = 3,
    trim_below: float = 0.25,
    confidence_threshold: float = 0.60,
    force: bool = False,
    timeout: int = 120,
) -> Result:
    source = input_path.resolve()
    diagnostics: list[Diagnostic] = []
    temp_context: tempfile.TemporaryDirectory[str] | None = None
    analysis_source = source
    if source.suffix.lower() == ".ly":
        analysis_source, temp_context, midi_diagnostics = _midi_from_lilypond(source, score_index, timeout)
        diagnostics.extend(midi_diagnostics)
    elif source.suffix.lower() not in {".xml", ".musicxml", ".mxl", ".mid", ".midi"}:
        raise WorkbenchError("Harmony analysis accepts LilyPond, MusicXML, or MIDI", "UNSUPPORTED_INPUT", exit_code=2)
    try:
        parsed = converter.parse(str(analysis_source))
        measured = parsed.makeMeasures(inPlace=False)
        chordified = measured.chordify()
        local_keys = _measure_keys(measured, window, key_override)
        reducer = analysis.reduceChords.ChordReducer()
        records: list[dict[str, Any]] = []
        chord_tokens: list[str] = []
        rhythm_tokens: list[str] = []
        roman_tokens: list[str] = []
        measures = list(chordified.getElementsByClass(stream.Measure))
        if not measures:
            measures = list(chordified.recurse().getElementsByClass(stream.Measure))
        for measure_index, measure in enumerate(measures):
            reduced = reducer.reduceMeasureToNChords(
                measure,
                maximumNumberOfChords=max_chords,
                weightAlgorithm=reducer.qlbsmpConsonance,
                trimBelow=trim_below,
            )
            measure_key = local_keys[min(measure_index, len(local_keys) - 1)]
            for event in reduced.notes:
                if not isinstance(event, chord.Chord):
                    event = chord.Chord(event.pitches)
                duration = _duration_suffix(event.quarterLength)
                try:
                    figure = harmony.chordSymbolFigureFromChord(event)
                except Exception:
                    figure = "Chord Symbol Cannot Be Identified"
                try:
                    roman_result = roman.romanNumeralFromChord(
                        event,
                        measure_key,
                        preferSecondaryDominants=False,
                    )
                    roman_figure = roman_result.figure
                    if event.commonName == "dominant seventh chord" and roman_result.scaleDegree != 5:
                        secondary = roman.romanNumeralFromChord(
                            event,
                            measure_key,
                            preferSecondaryDominants=True,
                        ).figure
                        if "/" in secondary:
                            roman_figure = secondary
                except Exception:
                    roman_figure = "?"
                confidence, reason = _confidence(event, figure)
                accepted = confidence >= confidence_threshold
                chord_tokens.append(_chord_token(event, duration) if accepted else f"s{duration}")
                rhythm_tokens.append(f"c'{duration}")
                roman_tokens.append(json.dumps(roman_figure if accepted else "", ensure_ascii=False))
                if not accepted:
                    diagnostics.append(
                        Diagnostic(
                            "warning",
                            "LOW_HARMONY_CONFIDENCE",
                            f"Measure {measure.number}, beat {float(event.offset) + 1:g}: {reason or 'low confidence'}",
                            file=str(source),
                            details={"figure": figure, "roman": roman_figure, "confidence": confidence},
                        )
                    )
                records.append(
                    {
                        "measure": measure.number,
                        "beat": float(event.offset) + 1,
                        "duration_quarters": float(event.quarterLength),
                        "local_key": str(measure_key),
                        "chord_symbol": figure if accepted else None,
                        "roman_numeral": roman_figure if accepted else None,
                        "inversion": event.inversion(),
                        "confidence": confidence,
                        "accepted": accepted,
                        "alternatives": [event.commonName],
                        "reason": reason,
                    }
                )
        if not records:
            raise WorkbenchError("No chord events could be reduced from the input", "NO_HARMONY_EVENTS")
        include_text = "\n".join(
            [
                '% Generated by lilypond-workbench; review low-confidence omissions in the JSON report.',
                'workbenchChordNames = \\chordmode {',
                f"  {' '.join(chord_tokens)}",
                '}',
                '',
                'workbenchRomanRhythm = {',
                f"  {' '.join(rhythm_tokens)}",
                '}',
                '',
                'workbenchRomanNumerals = \\lyricmode {',
                f"  {' '.join(roman_tokens)}",
                '}',
                '',
            ]
        )
        report = {
            "schema_version": 1,
            "source": str(source),
            "parameters": {
                "score_index": score_index,
                "key_override": key_override,
                "window": window,
                "max_chords_per_measure": max_chords,
                "trim_below": trim_below,
                "confidence_threshold": confidence_threshold,
            },
            "events": records,
        }
        output_destination = output_path.resolve()
        report_destination = (report_path or output_path.with_suffix(".analysis.json")).resolve()
        if not force:
            existing = [path for path in (output_destination, report_destination) if path.exists()]
            if existing:
                raise WorkbenchError(
                    f"Output already exists: {existing[0]}; pass --force to replace analysis outputs",
                    "OUTPUT_EXISTS",
                    exit_code=2,
                )
        atomic_write(output_destination, include_text, force=force)
        atomic_write(report_destination, json.dumps(report, ensure_ascii=False, indent=2) + "\n", force=force)
        return Result(
            True,
            "analyze-harmony",
            [str(source)],
            [str(output_destination), str(report_destination)],
            diagnostics,
            {"events": len(records), "accepted": sum(item["accepted"] for item in records)},
        )
    finally:
        if temp_context is not None:
            temp_context.cleanup()
