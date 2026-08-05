from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from .common import Diagnostic, Result, WorkbenchError, atomic_write, prepare_output
from .semantic import IndexedEvent, SemanticIndex, SourceLocation, build_semantic_index


HOME_CLEFS = {"violin": "treble", "viola": "alto", "cello": "bass"}
ALLOWED_CLEFS = {
    "violin": ("treble",),
    "viola": ("alto", "treble"),
    "cello": ("bass", "tenor", "treble"),
}
STAFF_RANGES = {
    "treble": (30, 38),  # E4--F5
    "alto": (26, 32),  # F3--G4
    "tenor": (22, 30),  # D3--E4
    "bass": (18, 26),  # G2--A3
}
PITCHES = {"C4": 28, "D4": 29, "G4": 32, "A4": 33, "B4": 34, "C5": 35}


@dataclass(frozen=True, slots=True)
class ClefTrackEvent:
    offset: Fraction
    clef: str
    origin: str
    source: SourceLocation | None = None


@dataclass(frozen=True, slots=True)
class ClefChange:
    offset: Fraction
    end: Fraction
    from_clef: str
    to_clef: str
    direction: str
    threshold: str
    ratio: float
    attacks: int
    current_cost: float
    target_cost: float
    source: SourceLocation
    reason: str


@dataclass(frozen=True, slots=True)
class ClefAnalysis:
    schema_version: int
    source: str
    variable: str
    instrument: str
    initial_clef: str
    duration: Fraction
    changes: tuple[ClefChange, ...]
    track: tuple[ClefTrackEvent, ...]
    diagnostics: tuple[Diagnostic, ...]
    index_fingerprint: str

    def to_dict(self, index: SemanticIndex | None = None) -> dict[str, Any]:
        def position(offset: Fraction) -> dict[str, Any]:
            return index.position(offset) if index is not None else {"offset": _fraction_text(offset)}

        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "variable": self.variable,
            "instrument": self.instrument,
            "initial_clef": self.initial_clef,
            "duration": _fraction_text(self.duration),
            "index_fingerprint": self.index_fingerprint,
            "changes": [
                {
                    "from": item.from_clef,
                    "to": item.to_clef,
                    "start": position(item.offset),
                    "end": position(item.end),
                    "direction": item.direction,
                    "threshold": item.threshold,
                    "ratio": round(item.ratio, 4),
                    "attacks": item.attacks,
                    "ledger_cost": {
                        "current": round(item.current_cost, 4),
                        "target": round(item.target_cost, 4),
                    },
                    "reason": item.reason,
                    "source": asdict(item.source),
                }
                for item in self.changes
            ],
            "track": [
                {
                    "clef": item.clef,
                    "position": position(item.offset),
                    "origin": item.origin,
                    "source": asdict(item.source) if item.source else None,
                }
                for item in self.track
            ],
            "diagnostics": [asdict(item) for item in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class _Rule:
    target: str
    direction: str
    threshold: int
    label: str


@dataclass(frozen=True, slots=True)
class _Window:
    end: Fraction
    ratio: float
    attacks: int
    current_cost: float
    target_cost: float
    source: SourceLocation


def _fraction_text(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def _ledger_lines(pitch: int, clef: str) -> int:
    bottom, top = STAFF_RANGES[clef]
    if pitch > top:
        return (pitch - top) // 2
    if pitch < bottom:
        return (bottom - pitch) // 2
    return 0


def _rules_for(instrument: str, current: str) -> tuple[_Rule, ...]:
    if instrument == "viola":
        if current == "alto":
            return (_Rule("treble", "up", PITCHES["C5"], "C5 or above"),)
        if current == "treble":
            return (_Rule("alto", "down", PITCHES["B4"], "B4 or below"),)
    if instrument == "cello":
        if current == "bass":
            return (
                _Rule("treble", "up", PITCHES["A4"], "A4 or above"),
                _Rule("tenor", "up", PITCHES["D4"], "D4 or above"),
            )
        if current == "tenor":
            return (
                _Rule("treble", "up", PITCHES["A4"], "A4 or above"),
                _Rule("bass", "down", PITCHES["C4"], "C4 or below"),
            )
        if current == "treble":
            return (
                _Rule("bass", "down", PITCHES["C4"], "C4 or below"),
                _Rule("tenor", "down", PITCHES["G4"], "G4 or below"),
            )
    return ()


def _beat_at(index: SemanticIndex, offset: Fraction) -> Fraction:
    return index.measure_at(offset).beat


def _safe_seams(index: SemanticIndex) -> list[Fraction]:
    seams = {Fraction(0), index.duration}
    seams.update(item.start for item in index.measures)
    seams.update(item.end for item in index.measures)
    seams.update(item.offset for item in index.markers if item.kind in {"seam", "clef"})
    for event in index.events:
        if event.kind == "rest" and event.duration >= _beat_at(index, event.offset):
            seams.add(event.end)
    return sorted(item for item in seams if 0 <= item <= index.duration)


def _weighted_stats(
    index: SemanticIndex,
    start: Fraction,
    end: Fraction,
    *,
    current: str,
    rule: _Rule,
) -> _Window | None:
    weighted = Fraction(0)
    qualifying = Fraction(0)
    attacks = 0
    current_cost = 0.0
    target_cost = 0.0
    first_event: IndexedEvent | None = None
    for event in index.events:
        if event.grace or event.cue or not event.pitches or event.end <= start or event.offset >= end:
            continue
        overlap = min(event.end, end) - max(event.offset, start)
        if overlap <= 0:
            continue
        if first_event is None:
            first_event = event
        if start <= event.offset < end:
            attacks += 1
        representative = max(event.pitches)
        weighted += overlap
        if (rule.direction == "up" and representative >= rule.threshold) or (
            rule.direction == "down" and representative <= rule.threshold
        ):
            qualifying += overlap
        event_cost_current = max(_ledger_lines(pitch, current) for pitch in event.pitches)
        event_cost_target = max(_ledger_lines(pitch, rule.target) for pitch in event.pitches)
        current_cost += float(overlap) * event_cost_current
        target_cost += float(overlap) * event_cost_target
    if not weighted or first_event is None:
        return None
    return _Window(
        end=end,
        ratio=float(qualifying / weighted),
        attacks=attacks,
        current_cost=current_cost / float(weighted),
        target_cost=target_cost / float(weighted),
        source=first_event.source,
    )


def _qualifying_window(
    index: SemanticIndex,
    seams: list[Fraction],
    start_index: int,
    *,
    current: str,
    rule: _Rule,
    locked_offsets: set[Fraction],
) -> _Window | None:
    start = seams[start_index]
    minimum = index.measure_at(start).meter
    for end in seams[start_index + 1 :]:
        if end in locked_offsets and end > start:
            break
        span = end - start
        if span < minimum:
            continue
        stats = _weighted_stats(index, start, end, current=current, rule=rule)
        if stats is None or stats.ratio < 0.70:
            continue
        if stats.attacks < 3 and span < minimum * 2:
            continue
        if rule.direction == "up" and stats.current_cost - stats.target_cost < 1.0:
            continue
        if rule.direction == "down" and stats.target_cost > stats.current_cost + 0.5:
            continue
        return stats
    return None


def _add_track(track: list[ClefTrackEvent], event: ClefTrackEvent) -> None:
    if track and track[-1].offset == event.offset:
        if track[-1].origin == "explicit" and event.origin != "explicit":
            return
        track[-1] = event
    elif not track or track[-1].clef != event.clef:
        track.append(event)


def analyze_clef_index(index: SemanticIndex, instrument: str, *, initial_clef: str | None = None) -> ClefAnalysis:
    instrument = instrument.lower().strip()
    if instrument not in HOME_CLEFS:
        raise WorkbenchError(
            f"Clef analysis supports violin, viola, and cello; received {instrument}",
            "UNSUPPORTED_INSTRUMENT",
            exit_code=2,
        )
    initial = (initial_clef or HOME_CLEFS[instrument]).strip('"')
    diagnostics = list(index.diagnostics)
    if initial not in ALLOWED_CLEFS[instrument]:
        diagnostics.append(
            Diagnostic(
                "warning",
                "CLEF_NONSTANDARD",
                f"{instrument.title()} normally starts in {HOME_CLEFS[instrument]}; preserving configured {initial} clef",
                file=index.source,
            )
        )
    explicit: dict[Fraction, ClefTrackEvent] = {}
    for marker in index.markers:
        if marker.kind != "clef":
            continue
        clef = marker.value.strip('"')
        explicit[marker.offset] = ClefTrackEvent(marker.offset, clef, "explicit", marker.source)
        if clef not in ALLOWED_CLEFS[instrument]:
            diagnostics.append(
                Diagnostic(
                    "warning",
                    "CLEF_NONSTANDARD",
                    f"{instrument.title()} normally uses {', '.join(ALLOWED_CLEFS[instrument])}; preserving explicit {clef} clef",
                    file=marker.source.file,
                    line=marker.source.line,
                    column=marker.source.column,
                )
            )
    seams = _safe_seams(index)
    locked_offsets = set(explicit)
    current = initial
    track: list[ClefTrackEvent] = [ClefTrackEvent(Fraction(0), initial, "initial")]
    changes: list[ClefChange] = []
    for seam_index, offset in enumerate(seams[:-1]):
        if offset in explicit:
            current = explicit[offset].clef
            _add_track(track, explicit[offset])
            continue
        for rule in _rules_for(instrument, current):
            window = _qualifying_window(
                index,
                seams,
                seam_index,
                current=current,
                rule=rule,
                locked_offsets=locked_offsets,
            )
            if window is None:
                continue
            reason = (
                f"{window.ratio:.0%} of the duration-weighted passage is {rule.label}; "
                f"ledger-line cost changes from {window.current_cost:.2f} to {window.target_cost:.2f}"
            )
            change = ClefChange(
                offset,
                window.end,
                current,
                rule.target,
                rule.direction,
                rule.label,
                window.ratio,
                window.attacks,
                window.current_cost,
                window.target_cost,
                window.source,
                reason,
            )
            changes.append(change)
            diagnostics.append(
                Diagnostic(
                    "info",
                    "CLEF_CHANGE_SUGGESTED",
                    f"Change {current} to {rule.target}: {reason}",
                    file=window.source.file,
                    line=window.source.line,
                    column=window.source.column,
                    details={
                        "from": current,
                        "to": rule.target,
                        "offset": _fraction_text(offset),
                        "window_end": _fraction_text(window.end),
                    },
                )
            )
            current = rule.target
            _add_track(track, ClefTrackEvent(offset, current, "recommended", window.source))
            break
    return ClefAnalysis(
        schema_version=1,
        source=index.source,
        variable=index.variable,
        instrument=instrument,
        initial_clef=initial,
        duration=index.duration,
        changes=tuple(changes),
        track=tuple(track),
        diagnostics=tuple(diagnostics),
        index_fingerprint=index.fingerprint,
    )


def analyze_clefs(
    source: Path,
    *,
    variable: str,
    instrument: str,
    output_path: Path,
    initial_clef: str | None = None,
    force: bool = False,
) -> Result:
    index = build_semantic_index(source, variable)
    analysis = analyze_clef_index(index, instrument, initial_clef=initial_clef)
    destination = prepare_output(output_path, force=force)
    atomic_write(destination, json.dumps(analysis.to_dict(index), ensure_ascii=False, indent=2) + "\n", force=True)
    return Result(
        True,
        "analyze-clefs",
        [str(source.resolve())],
        [str(destination)],
        list(analysis.diagnostics),
        {"changes": len(analysis.changes), "instrument": analysis.instrument, "variable": variable},
    )


def clef_track_name(part_id: str) -> str:
    words = [item for item in re.split(r"[^A-Za-z0-9]+", part_id) if item]
    suffix = "".join(item[:1].upper() + item[1:] for item in words) or "Part"
    return f"workbench{suffix}Clefs"


def render_clef_track(name: str, analysis: ClefAnalysis) -> str:
    lines = [f"{name} = {{"]
    cursor = Fraction(0)
    for event in analysis.track:
        if event.offset > cursor:
            lines.append(f"  {_skip(event.offset - cursor)}")
            cursor = event.offset
        lines.append(f"  \\clef {event.clef}")
    if analysis.duration > cursor:
        lines.append(f"  {_skip(analysis.duration - cursor)}")
    lines.extend(["}", ""])
    return "\n".join(lines)


def _skip(duration: Fraction) -> str:
    if duration == 1:
        return "s1"
    if duration.denominator == 1:
        return f"s1*{duration.numerator}"
    return f"s1*{duration.numerator}/{duration.denominator}"
