from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import ly.document
import ly.music
import ly.pitch.rel2abs
from ly.music import event as music_event
from ly.music import items

from .common import Diagnostic, WorkbenchError
from .syntax import find_command_blocks


INCLUDE_RE = re.compile(r'\\include\s+"([^"\n]+)"')


@dataclass(frozen=True, slots=True)
class SourceLocation:
    file: str
    line: int
    column: int
    offset: int


@dataclass(frozen=True, slots=True)
class IndexedEvent:
    kind: str
    offset: Fraction
    duration: Fraction
    pitches: tuple[int, ...]
    source: SourceLocation
    grace: bool = False
    cue: bool = False

    @property
    def end(self) -> Fraction:
        return self.offset + self.duration


@dataclass(frozen=True, slots=True)
class SemanticMarker:
    kind: str
    offset: Fraction
    value: str
    source: SourceLocation


@dataclass(frozen=True, slots=True)
class Measure:
    number: int
    start: Fraction
    end: Fraction
    meter: Fraction
    beat: Fraction
    complete: bool


@dataclass(frozen=True, slots=True)
class SemanticIndex:
    schema_version: int
    source: str
    variable: str
    fingerprint: str
    events: tuple[IndexedEvent, ...]
    markers: tuple[SemanticMarker, ...]
    measures: tuple[Measure, ...]
    duration: Fraction
    diagnostics: tuple[Diagnostic, ...]

    def measure_at(self, offset: Fraction) -> Measure:
        if not self.measures:
            return Measure(1, Fraction(0), max(self.duration, Fraction(1)), Fraction(1), Fraction(1, 4), False)
        for measure in self.measures:
            if measure.start <= offset < measure.end:
                return measure
        return self.measures[-1]

    def position(self, offset: Fraction) -> dict[str, Any]:
        measure = self.measure_at(offset)
        beat = (offset - measure.start) / measure.beat + 1
        return {"offset": _fraction_text(offset), "measure": measure.number, "beat": _fraction_text(beat)}

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "variable": self.variable,
            "fingerprint": self.fingerprint,
            "duration": _fraction_text(self.duration),
            "events": [
                {
                    "kind": item.kind,
                    "offset": _fraction_text(item.offset),
                    "duration": _fraction_text(item.duration),
                    "pitches": [_scientific_pitch(value) for value in item.pitches],
                    "diatonic_pitches": list(item.pitches),
                    "grace": item.grace,
                    "cue": item.cue,
                    "source": asdict(item.source),
                }
                for item in self.events
            ],
            "markers": [
                {
                    "kind": item.kind,
                    "offset": _fraction_text(item.offset),
                    "value": item.value,
                    "source": asdict(item.source),
                }
                for item in self.markers
            ],
            "measures": [
                {
                    "number": item.number,
                    "start": _fraction_text(item.start),
                    "end": _fraction_text(item.end),
                    "meter": _fraction_text(item.meter),
                    "beat": _fraction_text(item.beat),
                    "complete": item.complete,
                }
                for item in self.measures
            ],
        }


@dataclass(slots=True)
class _RawRecord:
    kind: str
    offset: Fraction
    duration: Fraction
    pitches: tuple[int, ...]
    value: str
    source: SourceLocation
    grace: bool = False


def _fraction_text(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def _scientific_pitch(diatonic: int) -> str:
    letters = "CDEFGAB"
    octave, note = divmod(diatonic, 7)
    return f"{letters[note]}{octave}"


def _document_location(node: items.Item) -> SourceLocation:
    document = node.document
    text = document.plaintext()
    offset = max(0, node.position)
    line = text.count("\n", 0, offset) + 1
    line_start = text.rfind("\n", 0, offset)
    column = offset - line_start
    filename = document.filename or "<memory>"
    return SourceLocation(str(Path(filename).expanduser().resolve()) if filename != "<memory>" else filename, line, column, offset)


def _pitch_position(pitch: Any) -> int:
    return (int(pitch.octave) + 3) * 7 + int(pitch.note)


def _absolute_copy(document: ly.document.Document) -> ly.document.Document:
    copied = document.copy()
    copied.filename = document.filename
    cursor = ly.document.Cursor(copied)
    cursor.select_all()
    ly.pitch.rel2abs.rel2abs(cursor, first_pitch_absolute=True)
    return copied


class _AbsoluteMusicDocument(items.Document):
    def get_music(self, filename: str) -> items.Document:
        document = ly.document.Document.load(filename)
        return type(self)(_absolute_copy(document))


def _load_tree(source: Path, *, absolute: bool) -> items.Document:
    document = ly.document.Document.load(str(source))
    if absolute:
        document = _absolute_copy(document)
        return _AbsoluteMusicDocument(document)
    return ly.music.document(document)


def _walk_documents(root: items.Document) -> Iterable[items.Document]:
    pending = [root]
    seen: set[str] = set()
    while pending:
        document = pending.pop()
        filename = document.document.filename or f"<memory:{id(document.document)}>"
        key = str(Path(filename).resolve()) if not filename.startswith("<memory:") else filename
        if key in seen:
            continue
        seen.add(key)
        yield document
        for node in document:
            if isinstance(node, items.Include):
                included = document.get_included_document_node(node)
                if included is not None:
                    pending.append(included)


def _find_assignment(root: items.Document, variable: str) -> items.Assignment:
    matches: list[items.Assignment] = []
    for document in _walk_documents(root):
        for node in document:
            if isinstance(node, items.Assignment) and str(node.name()) == variable:
                matches.append(node)
    if not matches:
        raise WorkbenchError(f"Music variable not found: {variable}", "VARIABLE_NOT_FOUND", exit_code=2)
    if len(matches) > 1:
        files = sorted({str(item.document.filename) for item in matches})
        raise WorkbenchError(
            f"Music variable {variable} is ambiguous across: {', '.join(files)}",
            "VARIABLE_AMBIGUOUS",
            exit_code=2,
        )
    if not isinstance(matches[0].value(), items.Music):
        raise WorkbenchError(f"Variable is not a music expression: {variable}", "VARIABLE_NOT_MUSIC", exit_code=2)
    return matches[0]


class _EventCollector(music_event.Events):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[_RawRecord] = []
        self._pitch_shift = 0
        self._commands: set[tuple[str, str]] = set()

    def _record(
        self,
        kind: str,
        node: items.Item,
        offset: Fraction,
        *,
        duration: Fraction = Fraction(0),
        pitches: tuple[int, ...] = (),
        value: str = "",
        grace: bool = False,
    ) -> None:
        self.records.append(
            _RawRecord(kind, Fraction(offset), Fraction(duration), pitches, value, _document_location(node), grace)
        )

    def traverse(self, node: items.Item, time: Fraction, scaling: Fraction) -> Fraction:
        time = Fraction(time)
        scaling = Fraction(scaling)
        if isinstance(node, items.Transpose):
            notes = [item for item in node if isinstance(item, items.Note)]
            music = [item for item in node if isinstance(item, items.Music)]
            shift = _pitch_position(notes[1].pitch) - _pitch_position(notes[0].pitch) if len(notes) >= 2 else 0
            previous = self._pitch_shift
            self._pitch_shift += shift
            try:
                for item in music[-1:]:
                    time = self.traverse(item, time, scaling)
                return time
            finally:
                self._pitch_shift = previous
        if isinstance(node, items.UserCommand):
            name = node.name()
            if name == "mark":
                self._record("seam", node, time, value="rehearsal")
            value = node.value()
            if value is None:
                return time
            filename = str(value.document.filename or "<memory>")
            key = (filename, name)
            if key in self._commands:
                return time
            self._commands.add(key)
            try:
                return self.traverse(value, time, scaling)
            finally:
                self._commands.remove(key)
        if isinstance(node, items.Chord):
            duration = Fraction(node.duration[0]) * Fraction(node.duration[1]) * scaling
            pitches = tuple(sorted(_pitch_position(item.pitch) + self._pitch_shift for item in node.find(items.Note)))
            if duration:
                self._record("chord", node, time, duration=duration, pitches=pitches, grace=scaling == 0)
            return time + duration
        if isinstance(node, items.Note):
            duration = Fraction(node.duration[0]) * Fraction(node.duration[1]) * scaling
            if duration:
                self._record(
                    "note",
                    node,
                    time,
                    duration=duration,
                    pitches=(_pitch_position(node.pitch) + self._pitch_shift,),
                    grace=scaling == 0,
                )
            return time + duration
        if isinstance(node, (items.Rest, items.Skip)):
            duration = Fraction(node.duration[0]) * Fraction(node.duration[1]) * scaling
            if duration:
                self._record("rest" if isinstance(node, items.Rest) else "skip", node, time, duration=duration)
            return time + duration
        if isinstance(node, items.Clef):
            self._record("clef", node, time, value=str(node.specifier()))
        elif isinstance(node, items.TimeSignature):
            self._record(
                "meter",
                node,
                time,
                duration=Fraction(node.measure_length()),
                value=f"{node.numerator()}/{Fraction(node.fraction()).denominator}",
            )
        elif isinstance(node, items.Partial):
            self._record("partial", node, time, duration=Fraction(node.partial_length()))
        elif isinstance(node, items.PipeSymbol):
            self._record("seam", node, time, value="barline")
        elif isinstance(node, items.PhrasingSlur):
            self._record("seam", node, time, value=f"phrase-{node.event}")
        elif isinstance(node, items.Command) and str(node.token) in {"\\mark", "\\bar"}:
            self._record("seam", node, time, value="rehearsal" if str(node.token) == "\\mark" else "barline")
        return node.events(self, time, scaling)


def _collect(assignment: items.Assignment) -> list[_RawRecord]:
    collector = _EventCollector()
    collector.read(assignment.value(), Fraction(0), Fraction(1))
    return collector.records


def _remap_locations(absolute: list[_RawRecord], original: list[_RawRecord]) -> tuple[list[_RawRecord], bool]:
    if len(absolute) != len(original) or any(left.kind != right.kind for left, right in zip(absolute, original, strict=False)):
        return absolute, False
    for target, source in zip(absolute, original, strict=True):
        target.source = source.source
    return absolute, True


def _dedupe_markers(records: Iterable[_RawRecord]) -> list[_RawRecord]:
    output: list[_RawRecord] = []
    seen: set[tuple[str, Fraction, str]] = set()
    for record in records:
        key = (record.kind, record.offset, record.value)
        if key not in seen:
            seen.add(key)
            output.append(record)
    return output


def _meter_at(meters: list[_RawRecord], offset: Fraction) -> tuple[Fraction, Fraction]:
    active = next((item for item in reversed(meters) if item.offset <= offset), None)
    if active is None:
        return Fraction(1), Fraction(1, 4)
    denominator = int(active.value.split("/", 1)[1]) if "/" in active.value else 4
    return active.duration, Fraction(1, denominator)


def _build_measures(records: list[_RawRecord], duration: Fraction) -> tuple[Measure, ...]:
    meters = sorted(_dedupe_markers(item for item in records if item.kind == "meter"), key=lambda item: item.offset)
    partials = sorted((item for item in records if item.kind == "partial"), key=lambda item: item.offset)
    changes = sorted({item.offset for item in meters if item.offset > 0})
    measures: list[Measure] = []
    start = Fraction(0)
    number = 1
    first = True
    while start < duration:
        meter, beat = _meter_at(meters, start)
        length = partials[0].duration if first and partials and partials[0].offset == 0 else meter
        planned_end = start + length
        intervening = next((item for item in changes if start < item < planned_end), None)
        end = min(intervening or planned_end, duration)
        measures.append(Measure(number, start, end, meter, beat, end - start == length))
        start = end
        number += 1
        first = False
    return tuple(measures)


def _local_dependencies(source: Path) -> list[Path]:
    pending = [source.resolve()]
    seen: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        text = path.read_text(encoding="utf-8")
        for match in INCLUDE_RE.finditer(text):
            included = (path.parent / match.group(1)).resolve()
            if included.is_file():
                pending.append(included)
    return sorted(seen)


def _cue_ranges(source: Path) -> dict[str, list[tuple[int, int]]]:
    ranges: dict[str, list[tuple[int, int]]] = {}
    for path in _local_dependencies(source):
        text = path.read_text(encoding="utf-8")
        blocks = [
            block
            for command in ("cueDuring", "cueDuringWithClef")
            for block in find_command_blocks(text, command)
        ]
        if blocks:
            ranges[str(path)] = [(item.open_brace, item.close_brace) for item in blocks]
    return ranges


def semantic_fingerprint(source: Path) -> str:
    digest = hashlib.sha256()
    for path in _local_dependencies(source):
        digest.update(str(path).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


@lru_cache(maxsize=32)
def _cached_index(source_name: str, variable: str, fingerprint: str) -> SemanticIndex:
    source = Path(source_name)
    original_root = _load_tree(source, absolute=False)
    absolute_root = _load_tree(source, absolute=True)
    original_assignment = _find_assignment(original_root, variable)
    absolute_assignment = _find_assignment(absolute_root, variable)
    original_records = _collect(original_assignment)
    absolute_records = _collect(absolute_assignment)
    records, mapped = _remap_locations(absolute_records, original_records)
    diagnostics: list[Diagnostic] = []
    if not mapped:
        diagnostics.append(
            Diagnostic(
                "warning",
                "SEMANTIC_SOURCE_MAP",
                "Absolute-pitch parsing changed the event structure; some source columns may refer to the normalized copy",
                file=str(source),
            )
        )
    cue_ranges = _cue_ranges(source)
    events = tuple(
        IndexedEvent(
            item.kind,
            item.offset,
            item.duration,
            item.pitches,
            item.source,
            item.grace,
            any(start <= item.source.offset <= end for start, end in cue_ranges.get(item.source.file, [])),
        )
        for item in records
        if item.kind in {"note", "chord", "rest", "skip"}
    )
    marker_records = _dedupe_markers(item for item in records if item.kind not in {"note", "chord", "rest", "skip"})
    markers = tuple(SemanticMarker(item.kind, item.offset, item.value, item.source) for item in marker_records)
    duration = max((item.end for item in events), default=Fraction(0))
    return SemanticIndex(
        schema_version=1,
        source=str(source),
        variable=variable,
        fingerprint=fingerprint,
        events=events,
        markers=markers,
        measures=_build_measures(records, duration),
        duration=duration,
        diagnostics=tuple(diagnostics),
    )


def build_semantic_index(source: Path, variable: str) -> SemanticIndex:
    resolved = source.expanduser().resolve()
    return _cached_index(str(resolved), variable, semantic_fingerprint(resolved))
