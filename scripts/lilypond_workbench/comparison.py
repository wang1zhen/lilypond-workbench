from __future__ import annotations

import json
from dataclasses import dataclass
from difflib import SequenceMatcher
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable, Sequence

from .common import Diagnostic, Result, WorkbenchError, atomic_write, prepare_output
from .semantic import IndexedEvent, SemanticIndex, SemanticMarker, build_semantic_index, pitch_label


DIFF_SCHEMA_VERSION = 1
_DIAGNOSTIC_LIMIT = 100


@dataclass(frozen=True, slots=True)
class Change:
    """One musical difference, located in whichever sides contain it."""

    kind: str
    detail: str
    measures: tuple[int, ...]
    old: dict[str, Any] | None
    new: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "detail": self.detail,
            "measures": list(self.measures),
            "old": self.old,
            "new": self.new,
        }


def parse_measure_selection(text: str) -> set[int]:
    """Parse "12,37-40" into a set of measure numbers."""
    selected: set[int] = set()
    for part in text.split(","):
        item = part.strip()
        if not item:
            continue
        if "-" in item.lstrip("-"):
            first, _, last = item.partition("-")
            try:
                start, end = int(first), int(last)
            except ValueError:
                raise WorkbenchError(f"Invalid measure range: {item}", "INVALID_ARGUMENT", exit_code=2) from None
            if start > end:
                raise WorkbenchError(f"Measure range is reversed: {item}", "INVALID_ARGUMENT", exit_code=2)
            selected.update(range(start, end + 1))
            continue
        try:
            selected.add(int(item))
        except ValueError:
            raise WorkbenchError(f"Invalid measure number: {item}", "INVALID_ARGUMENT", exit_code=2) from None
    if not selected:
        raise WorkbenchError("Measure selection is empty", "INVALID_ARGUMENT", exit_code=2)
    return selected


def _event_identity(event: IndexedEvent) -> tuple[Any, ...]:
    """What makes two events the same music, ignoring where they sit."""
    return (event.kind, event.pitches, event.alters, event.duration, event.grace)


def _marker_identity(marker: SemanticMarker) -> tuple[Any, ...]:
    return (marker.kind, marker.value)


def _event_side(index: SemanticIndex, event: IndexedEvent) -> dict[str, Any]:
    position = index.position(event.offset)
    return {
        "kind": event.kind,
        "pitches": _pitch_names(event),
        "duration": _fraction_text(event.duration),
        "grace": event.grace,
        **position,
        "file": event.source.file,
        "line": event.source.line,
        "column": event.source.column,
    }


def _marker_side(index: SemanticIndex, marker: SemanticMarker) -> dict[str, Any]:
    return {
        "kind": marker.kind,
        "value": marker.value,
        **index.position(marker.offset),
        "file": marker.source.file,
        "line": marker.source.line,
        "column": marker.source.column,
    }


def _fraction_text(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def _pitch_names(event: IndexedEvent) -> list[str]:
    alters = event.alters or (Fraction(0),) * len(event.pitches)
    return [pitch_label(value, alter) for value, alter in zip(event.pitches, alters)]


def _describe(side: dict[str, Any]) -> str:
    if "pitches" in side:
        pitches = "/".join(side["pitches"]) or side["kind"]
        return f"{pitches} for {side['duration']}"
    return f"{side['kind']} {side['value']}".strip()


def _measures_of(*sides: dict[str, Any] | None) -> tuple[int, ...]:
    return tuple(sorted({side["measure"] for side in sides if side is not None}))


def _pair_change(
    old_index: SemanticIndex,
    new_index: SemanticIndex,
    old_item: IndexedEvent,
    new_item: IndexedEvent,
) -> Change | None:
    old_side = _event_side(old_index, old_item)
    new_side = _event_side(new_index, new_item)
    differences: list[str] = []
    if old_item.kind != new_item.kind:
        differences.append(f"{old_item.kind} became {new_item.kind}")
    if (old_item.pitches, old_item.alters) != (new_item.pitches, new_item.alters):
        differences.append(
            f"pitch {'/'.join(old_side['pitches']) or 'none'} became {'/'.join(new_side['pitches']) or 'none'}"
        )
    if old_item.duration != new_item.duration:
        differences.append(f"duration {old_side['duration']} became {new_side['duration']}")
    if old_item.grace != new_item.grace:
        differences.append("grace status changed")
    if not differences:
        return None
    kind = "event_changed"
    if len(differences) == 1 and (old_item.pitches, old_item.alters) != (new_item.pitches, new_item.alters):
        kind = "pitch_changed"
    elif len(differences) == 1 and old_item.duration != new_item.duration:
        kind = "duration_changed"
    return Change(kind, "; ".join(differences), _measures_of(old_side, new_side), old_side, new_side)


def _compare(
    old_index: SemanticIndex,
    new_index: SemanticIndex,
    old_items: Sequence[Any],
    new_items: Sequence[Any],
    *,
    identity,
    side,
    added: str,
    removed: str,
    changed=None,
) -> list[Change]:
    matcher = SequenceMatcher(
        None,
        [identity(item) for item in old_items],
        [identity(item) for item in new_items],
        autojunk=False,
    )
    changes: list[Change] = []
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        old_slice = old_items[old_start:old_end]
        new_slice = new_items[new_start:new_end]
        if tag == "replace" and changed is not None and len(old_slice) == len(new_slice):
            for old_item, new_item in zip(old_slice, new_slice, strict=True):
                change = changed(old_index, new_index, old_item, new_item)
                if change is not None:
                    changes.append(change)
            continue
        for item in old_slice:
            old_side = side(old_index, item)
            changes.append(Change(removed, f"removed {_describe(old_side)}", _measures_of(old_side), old_side, None))
        for item in new_slice:
            new_side = side(new_index, item)
            changes.append(Change(added, f"added {_describe(new_side)}", _measures_of(new_side), None, new_side))
    return changes


def _sort_key(change: Change) -> tuple[Any, ...]:
    side = change.new or change.old or {}
    return (change.measures[0] if change.measures else 0, str(side.get("beat", "")), change.kind)


def _changed_measures(changes: Iterable[Change]) -> tuple[int, ...]:
    return tuple(sorted({measure for change in changes for measure in change.measures}))


def diff_scores(
    old_path: Path,
    new_path: Path,
    *,
    variable: str,
    new_variable: str | None = None,
    output_path: Path | None = None,
    expect_measures: str | None = None,
    fail_on_change: bool = False,
    force: bool = False,
) -> Result:
    """Compare two scores by what they sound like, not by their text.

    Text diffs are close to useless for LilyPond: one edited pitch inside
    \\relative silently shifts everything after it, and a reformat changes every
    line while changing no music.  This walks both semantic indexes instead, so
    the report is in measures and beats.
    """
    old_index = build_semantic_index(old_path, variable)
    new_index = build_semantic_index(new_path, new_variable or variable)
    diagnostics = [*old_index.diagnostics, *new_index.diagnostics]

    changes = _compare(
        old_index,
        new_index,
        old_index.events,
        new_index.events,
        identity=_event_identity,
        side=_event_side,
        added="event_added",
        removed="event_removed",
        changed=_pair_change,
    )
    changes.extend(
        _compare(
            old_index,
            new_index,
            old_index.markers,
            new_index.markers,
            identity=_marker_identity,
            side=_marker_side,
            added="marker_added",
            removed="marker_removed",
        )
    )
    changes.sort(key=_sort_key)
    touched = _changed_measures(changes)

    identical = not changes

    # Report every change through the diagnostic channel too, so the terminal
    # output is readable and each difference carries a source location.
    for change in changes[:_DIAGNOSTIC_LIMIT]:
        side = change.new or change.old or {}
        diagnostics.append(
            Diagnostic(
                "info",
                f"DIFF_{change.kind.upper()}",
                f"measure {side.get('measure', '?')} beat {side.get('beat', '?')}: {change.detail}",
                file=side.get("file"),
                line=side.get("line"),
                column=side.get("column"),
            )
        )
    if len(changes) > _DIAGNOSTIC_LIMIT:
        diagnostics.append(
            Diagnostic(
                "info",
                "DIFF_TRUNCATED",
                f"{len(changes) - _DIAGNOSTIC_LIMIT} further change(s) are listed in the report only",
                file=str(new_path),
                suggestion="Use --output or --json to read the complete comparison.",
            )
        )

    ok = True
    if fail_on_change and changes:
        ok = False
        diagnostics.append(
            Diagnostic(
                "error",
                "DIFF_UNEXPECTED_CHANGE",
                f"{len(changes)} semantic change(s) found in measure(s) {', '.join(str(item) for item in touched)}",
                file=str(new_path),
                suggestion="Drop --fail-on-change to report the differences instead of failing on them.",
            )
        )
    allowed: set[int] | None = parse_measure_selection(expect_measures) if expect_measures else None
    if allowed is not None:
        for change in changes:
            outside = [measure for measure in change.measures if measure not in allowed]
            if not outside:
                continue
            ok = False
            side = change.new or change.old or {}
            diagnostics.append(
                Diagnostic(
                    "error",
                    "DIFF_OUTSIDE_EXPECTED",
                    f"Unexpected change in measure {outside[0]}: {change.detail}",
                    file=side.get("file"),
                    line=side.get("line"),
                    column=side.get("column"),
                    suggestion="Widen --expect-measures or revert the change outside the intended range.",
                )
            )

    report = {
        "schema_version": DIFF_SCHEMA_VERSION,
        "old": _side_summary(old_path, old_index),
        "new": _side_summary(new_path, new_index),
        "identical": identical,
        "expect_measures": sorted(allowed) if allowed is not None else None,
        "summary": {
            "changes": len(changes),
            "changed_measures": list(touched),
            "by_kind": _counts(changes),
            "duration_changed": old_index.duration != new_index.duration,
        },
        "changes": [change.to_dict() for change in changes],
    }
    artifacts: list[str] = []
    if output_path is not None:
        destination = prepare_output(output_path, force=force)
        atomic_write(destination, json.dumps(report, ensure_ascii=False, indent=2) + "\n", force=True)
        artifacts.append(str(destination))
    return Result(
        ok,
        "diff",
        [str(old_index.source), str(new_index.source)],
        artifacts,
        diagnostics,
        {"report": report},
    )


def _side_summary(path: Path, index: SemanticIndex) -> dict[str, Any]:
    return {
        "source": str(path),
        "variable": index.variable,
        "fingerprint": index.fingerprint,
        "duration": _fraction_text(index.duration),
        "events": len(index.events),
        "markers": len(index.markers),
        "measures": len(index.measures),
    }


def _counts(changes: Iterable[Change]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for change in changes:
        counts[change.kind] = counts.get(change.kind, 0) + 1
    return dict(sorted(counts.items()))


def index_score(
    source: Path,
    *,
    variable: str,
    output_path: Path | None = None,
    force: bool = False,
) -> Result:
    """Expose the semantic index that lint and analyze-clefs consume internally."""
    index = build_semantic_index(source, variable)
    report = index.to_dict()
    artifacts: list[str] = []
    if output_path is not None:
        destination = prepare_output(output_path, force=force)
        atomic_write(destination, json.dumps(report, ensure_ascii=False, indent=2) + "\n", force=True)
        artifacts.append(str(destination))
    return Result(
        not any(item.severity == "error" for item in index.diagnostics),
        "index",
        [str(index.source)],
        artifacts,
        list(index.diagnostics),
        {"report": report},
    )
