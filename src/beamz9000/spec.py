"""
BeamSpec: the engine-neutral description of a beam that diagrams are drawn from.

The diagram code never sees the YAML scheme. It reads a BeamSpec: node
locations, supports and loads as plain floats, each load carrying the legend
key it is drawn under and the labels to show. An analysis engine (Pynite,
pycba, ...) only needs an adapter that produces one.

Floats are SI base units (m, N, N/m, N·m) when the scheme used quantities, and
the scheme's own numbers when it used plain numbers. Labels keep the
engineer's display units.

Sign conventions: positive forces act downward; positive moments are
counter-clockwise.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from beamz9000 import units
from beamz9000.scheme import Beam, SupportType

FACTORED = "Factored"

KeyKind = Literal["case", "occupancy", "factored"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SpecLoad(_Frozen):
    """One drawn load."""

    kind: Literal["point", "moment", "line"]
    key: str = Field(description="Legend key: a load case, an occupancy, or 'Factored'.")
    x1: float
    x2: Optional[float] = None
    mag1: float
    mag2: Optional[float] = None
    label1: str = Field(description="Label for the load, or for its start if label2 is given.")
    label2: Optional[str] = Field(None, description="Label for the end of a varying line load.")
    area_load: bool = Field(False, description="True for line loads from pressures (drawn hatched).")
    angle: float = Field(0.0, description="Point loads: degrees from vertical; + tilts the tail CCW.")


class LegendKey(_Frozen):
    name: str
    kind: KeyKind


class BeamSpec(_Frozen):
    """Everything a beam diagram needs, as plain values."""

    name: Optional[str] = None
    nodes: list[float]
    supports: list[SupportType]
    support_labels: list[Optional[str]] = Field(
        default_factory=list, description="Per node: a spring's stiffness label, else None."
    )
    node_labels: list[Optional[str]] = Field(default_factory=list, description="Per node; None for no label.")
    depth: Optional[float] = Field(None, description="Drawn beam depth; None draws a line.")
    loads: list[SpecLoad] = Field(default_factory=list)
    keys: list[LegendKey] = Field(default_factory=list, description="Legend keys in drawing order.")
    span_labels: list[str]
    length_label: str

    @property
    def length(self) -> float:
        return self.nodes[-1] - self.nodes[0]

    @property
    def spans(self) -> list[float]:
        return [b - a for a, b in zip(self.nodes, self.nodes[1:])]


def from_scheme(beam: Beam, name: Optional[str] = None, split_occupancies: bool = False) -> BeamSpec:
    """
    Returns the BeamSpec for a scheme Beam.

    A pressure load naming an occupancy is drawn as one load under the
    occupancy's key, at the occupancy's total pressure. With
    'split_occupancies', it is drawn as one load per case under each case's
    key instead.
    """
    loads: list[SpecLoad] = []
    keys: dict[str, KeyKind] = {}
    resolved = beam.resolved_loads
    done_occupancy_loads: set[int] = set()

    for r in resolved:
        if r.occupancy is not None and not split_occupancies:
            if r.index in done_occupancy_loads:
                continue
            done_occupancy_loads.add(r.index)
            parts = [p for p in resolved if p.index == r.index]
            if len(parts) > 1:
                loads.append(_combined_occupancy(r.occupancy, parts))
                keys.setdefault(r.occupancy, "occupancy")
                continue
        key = r.case if r.case is not None else FACTORED
        keys.setdefault(key, "case" if r.case is not None else "factored")
        loads.append(_spec_load(r, key))

    return BeamSpec(
        name=name,
        nodes=[units.si(n) for n in beam.nodes],
        supports=beam.node_supports,
        support_labels=[_stiffness_label(s) for s in beam.support_specs],
        node_labels=beam.labels,
        depth=units.si(beam.depth) if beam.depth is not None else None,
        loads=loads,
        keys=[LegendKey(name=k, kind=v) for k, v in keys.items()],
        span_labels=[units.label(s) for s in beam.spans],
        length_label=units.label(beam.length),
    )


def _stiffness_label(support) -> Optional[str]:
    if support.k is None:
        return None
    text = units.label(support.k)
    if support.type == "rotational_spring" and units.is_quantity(support.k):
        text += "/rad"
    return text


def _spec_load(r, key: str) -> SpecLoad:
    common = dict(kind=r.kind, key=key, x1=units.si(r.x1), mag1=units.si(r.mag1))
    if r.kind != "line":
        return SpecLoad(**common, label1=r.label or units.magnitude_label(r.mag1), angle=r.angle)
    mag2 = units.si(r.mag2)
    if r.pressure is not None:
        labels = (r.label or units.magnitude_label(r.pressure), None)
    elif r.label is not None or units.si(r.mag1) == mag2:
        labels = (r.label or units.magnitude_label(r.mag1), None)
    else:
        labels = (units.magnitude_label(r.mag1), units.magnitude_label(r.mag2))
    return SpecLoad(
        **common, x2=units.si(r.x2), mag2=mag2, label1=labels[0], label2=labels[1],
        area_load=r.pressure is not None,
    )


def _combined_occupancy(occupancy: str, parts) -> SpecLoad:
    first = parts[0]
    total_q = parts[0].pressure
    mag1, mag2 = parts[0].mag1, parts[0].mag2
    for p in parts[1:]:
        total_q = units.add(total_q, p.pressure)
        mag1, mag2 = units.add(mag1, p.mag1), units.add(mag2, p.mag2)
    return SpecLoad(
        kind="line", key=occupancy, x1=units.si(first.x1), x2=units.si(first.x2),
        mag1=units.si(mag1), mag2=units.si(mag2),
        label1=first.label or units.magnitude_label(total_q), area_load=True,
    )
