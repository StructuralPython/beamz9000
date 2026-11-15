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

When the scheme lists `results`, the beam is analysed (see
`beamz9000.analysis`) and the spec also carries each support's reactions per
load case and the result diagrams, with the labels to draw.
"""

from __future__ import annotations

import warnings
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from beamz9000 import units
from beamz9000.scheme import Beam, SupportType

KeyKind = Literal["case", "occupancy"]

# What a result line or curve stands for: one load case, or the largest or
# smallest value over the load combinations.
Role = Literal["case", "max", "min"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SpecLoad(_Frozen):
    """One drawn load."""

    kind: Literal["point", "moment", "line"]
    key: Optional[str] = Field(
        description="Legend key: a load case or an occupancy. None for a load without a case "
        "(drawn in ink, with no legend entry).",
    )
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
    detail: Optional[str] = Field(
        None, description="Shown after the name, e.g. the pressures of an occupancy: 'D 2 kPa, L 2.4 kPa'.",
    )

    @property
    def text(self) -> str:
        """The legend entry: the name, then the detail in parentheses."""
        return self.name if not self.detail else f"{self.name} ({self.detail})"


class SpecReaction(_Frozen):
    """
    One support's reactions in one load case, or its factored max or min over
    the force combinations. Up, right and counter-clockwise are positive; a
    max or min line holds each component's max or min.
    """

    node: int
    key: Optional[str] = Field(description="The load case, drawn in its legend colour; None in ink.")
    role: Role = "case"
    fy: float
    mz: float = 0.0
    fx: float = 0.0
    label: str = Field(description="The reactions as drawn, e.g. '↑ 12.3 kN  ↺ 4.5 kN·m'.")


class SpecCurve(_Frozen):
    """One load case's values along the beam, or the max or min of an envelope (key None)."""

    key: Optional[str]
    role: Role = "case"
    x: list[float]
    y: list[float]


class SpecPeak(_Frozen):
    key: Optional[str]
    role: Role = "case"
    x: float
    y: float
    label: str


DiagramKind = Literal["shear", "moment", "deflection", "rotation"]

DIAGRAM_TITLES = {"shear": "Shear", "moment": "Moment", "deflection": "Deflection", "rotation": "Rotation"}


class SpecDiagram(_Frozen):
    """
    A result diagram: one curve per load case, or the max and min curves of an
    envelope over the load combinations, and labelled peaks. Values are
    as computed (shear up positive, moment sagging positive, deflection up
    positive, rotation counter-clockwise positive); the drawing decides which
    way is up.
    """

    kind: DiagramKind
    title: str
    curves: list[SpecCurve]
    peaks: list[SpecPeak] = Field(default_factory=list)
    envelope: bool = Field(False, description="True for a factored envelope over the load combinations.")


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
    reactions: list[SpecReaction] = Field(default_factory=list, description="From an analysis, if any.")
    diagrams: list[SpecDiagram] = Field(default_factory=list, description="Result diagrams, in order.")

    @property
    def length(self) -> float:
        return self.nodes[-1] - self.nodes[0]

    @property
    def spans(self) -> list[float]:
        return [b - a for a, b in zip(self.nodes, self.nodes[1:])]


def from_scheme(beam: Beam, name: Optional[str] = None, split_occupancies: bool = False,
                analyze: bool = True) -> BeamSpec:
    """
    Returns the BeamSpec for a scheme Beam.

    A pressure load naming an occupancy is drawn as one load under the
    occupancy's key, at the occupancy's total pressure, labelled with its trib width(s). With
    'split_occupancies', it is drawn as one load per case under each case's
    key instead.

    With 'analyze' and `results` in the scheme, the beam is analysed and the
    spec carries its reactions and result diagrams. Without an analysis
    engine installed, it is drawn without them, with a warning.
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
        if r.case is not None:
            keys.setdefault(r.case, "case")
        loads.append(_spec_load(r, r.case))

    details = _pressure_details(beam, resolved, keys)
    reactions, diagrams = [], []
    if analyze and beam.results.requested:
        result = _analyze(beam)
        if result is not None:
            for case in result.cases:
                if case is not None:
                    keys.setdefault(case, "case")
            shown = _result_units(beam)
            reactions = _reactions(result, shown) if beam.results.reactions else []
            diagrams = _diagrams(result, beam.results.diagrams, shown, list(keys))

    return BeamSpec(
        name=name,
        nodes=[units.si(n) for n in beam.nodes],
        supports=beam.node_supports,
        support_labels=[_stiffness_label(s) for s in beam.support_specs],
        node_labels=beam.labels,
        depth=units.si(beam.depth) if beam.depth is not None else None,
        loads=loads,
        keys=[LegendKey(name=k, kind=v, detail=details.get(k)) for k, v in keys.items()],
        span_labels=[units.label(s) for s in beam.spans],
        length_label=units.label(beam.length),
        reactions=reactions,
        diagrams=diagrams,
    )


# --- Results ----------------------------------------------------------------------------


def _analyze(beam: Beam):
    from beamz9000 import analysis

    try:
        return analysis.analyze(beam, list(beam.results.diagrams), beam.results.engine)
    except ImportError as err:
        warnings.warn(f"{err}; drawing the beam without results", stacklevel=3)
        return None


def _result_units(beam: Beam) -> Optional[dict[str, str]]:
    """Display units for results, or None for a scheme in plain numbers."""
    if not any(units.is_quantity(s) for s in beam.spans):
        return None
    values: dict[str, list] = {"length": list(beam.spans)}
    for load in beam.loads:
        kind = {"point": "force", "moment": "moment", "dist": "line_load", "pressure": "pressure"}[load.type]
        values.setdefault(kind, []).extend(v for k, v in load if k.startswith("mag") and units.is_quantity(v))
    for pressures in beam.occupancies.values():
        values.setdefault("pressure", []).extend(pressures.values())
    return units.result_units(values)


def _fmt(value: float, kind: str, shown: Optional[dict[str, str]], signed: bool = True) -> str:
    unit = None if shown is None else shown["rotation" if kind == "rotation" else kind]
    if kind == "rotation" and unit is not None:
        return f"{units.result_label(value, kind, None, signed)} rad"
    return units.result_label(value, kind, unit, signed)


def _reaction_label(fy: float, fx: float, mz: float, shown) -> str:
    parts = []
    if fy:
        parts.append(("↑ " if fy > 0 else "↓ ") + _fmt(fy, "force", shown, signed=False))
    if fx:
        parts.append(("→ " if fx > 0 else "← ") + _fmt(fx, "force", shown, signed=False))
    if mz:
        parts.append(("↺ " if mz > 0 else "↻ ") + _fmt(mz, "moment", shown, signed=False))
    return "  ".join(parts) or "0"


def _reactions(result, shown) -> list[SpecReaction]:
    """
    Each support's reactions per load case and, with force combinations,
    its factored max and min ('max ↑ 40 kN', 'min ↑ 12 kN').
    """
    out = [
        SpecReaction(node=r.node, key=r.case, fy=r.fy, mz=r.mz, fx=r.fx,
                     label=_reaction_label(r.fy, r.fx, r.mz, shown))
        for r in result.reactions if r.case in result.cases
    ]
    for env in result.reaction_envelopes():
        for i, role in enumerate(("max", "min")):
            fy, mz, fx = env.fy[i], env.mz[i], env.fx[i]
            out.append(SpecReaction(node=env.node, key=None, role=role, fy=fy, mz=mz, fx=fx,
                                    label=f"{role} " + _reaction_label(fy, fx, mz, shown)))
    return out


_DIAGRAM_UNITS = {"shear": "force", "moment": "moment", "deflection": "length", "rotation": "rotation"}


def _clean(value: float, biggest: float) -> float:
    """'value' with round-off (a millionth of the diagram's largest value) snapped to 0."""
    return 0.0 if abs(value) <= 1e-6 * biggest else value


def _diagrams(result, kinds, shown, key_order) -> list[SpecDiagram]:
    order = {k: i for i, k in enumerate(key_order)}
    # Loads without a case (None) first, then the cases in legend order.
    cases = sorted(result.cases, key=lambda c: -1 if c is None else order.get(c, len(order)))
    out = []
    for kind in kinds:
        envelope = result.envelope(kind)
        if envelope is not None:
            out.append(_envelope_diagram(kind, envelope, shown))
            continue
        curves = [c for case in cases for c in result.curves if c.quantity == kind and c.case == case]
        if not curves:
            continue
        # Every curve lists its max and min, even when one is small or zero, so
        # no result looks missing. A constant curve lists its one value.
        biggest = max((abs(v) for c in curves for v in c.y), default=0.0)
        peaks = []
        for c in curves:
            for pick in (max, min):
                i = pick(range(len(c.y)), key=lambda j: c.y[j])
                value = _clean(c.y[i], biggest)
                if any(p.key == c.case and p.x == c.x[i] for p in peaks):
                    continue
                peaks.append(SpecPeak(key=c.case, x=c.x[i], y=value, label=_fmt(value, _DIAGRAM_UNITS[kind], shown)))
        out.append(SpecDiagram(
            kind=kind, title=DIAGRAM_TITLES[kind],
            curves=[SpecCurve(key=c.case, x=list(c.x), y=list(c.y)) for c in curves],
            peaks=peaks,
        ))
    return out


def _envelope_diagram(kind: str, env, shown) -> SpecDiagram:
    """The max and min curves over the combinations, each with its extreme value labelled."""
    curves = [SpecCurve(key=None, role="max", x=list(env.x), y=list(env.max)),
              SpecCurve(key=None, role="min", x=list(env.x), y=list(env.min))]
    peaks = []  # Always both, even when one is small or zero, so no result looks missing.
    for role, ys, pick in (("max", env.max, max), ("min", env.min, min)):
        i = pick(range(len(ys)), key=lambda j: ys[j])
        peaks.append(SpecPeak(key=None, role=role, x=env.x[i], y=ys[i],
                                  label=_fmt(ys[i], _DIAGRAM_UNITS[kind], shown)))
    return SpecDiagram(kind=kind, title=f"{DIAGRAM_TITLES[kind]} envelope",
                       curves=curves, peaks=peaks, envelope=True)


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
        labels = (r.label, None) if r.label is not None else _trib_labels(r.trib1, r.trib2)
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
    mag1, mag2 = parts[0].mag1, parts[0].mag2
    label1, label2 = (first.label, None) if first.label is not None else _trib_labels(first.trib1, first.trib2)
    for p in parts[1:]:
        mag1, mag2 = units.add(mag1, p.mag1), units.add(mag2, p.mag2)
    return SpecLoad(
        kind="line", key=occupancy, x1=units.si(first.x1), x2=units.si(first.x2),
        mag1=units.si(mag1), mag2=units.si(mag2),
        label1=label1, label2=label2, area_load=True,
    )


def _trib_labels(trib1, trib2) -> tuple[str, Optional[str]]:
    """A pressure load's label(s): its tributary width, or the width at each end if it varies."""
    if units.si(trib1) == units.si(trib2):
        return units.label(trib1), None
    return units.label(trib1), units.label(trib2)


def _pressure_details(beam: Beam, resolved, keys: dict) -> dict[str, str]:
    """
    The pressures behind each legend key, now that pressure loads are labelled
    with their trib widths: an occupancy lists its pressure per case
    ('D 2 kPa, L 2.4 kPa'), and a case lists the pressures of its own pressure
    loads ('1.2 kPa').
    """
    details: dict[str, list[str]] = {}
    for name, pressures in beam.occupancies.items():
        if keys.get(name) == "occupancy":
            details[name] = [f"{case} {units.label(q)}" for case, q in pressures.items()]
    for r in resolved:
        if r.pressure is None or (r.occupancy is not None and keys.get(r.occupancy) == "occupancy"):
            continue
        if r.case is None:
            continue
        key = r.case
        text = units.label(r.pressure)
        if text not in details.setdefault(key, []):
            details[key].append(text)
    return {k: ", ".join(v) for k, v in details.items() if v}
