"""
Analyses a scheme Beam with pycba (through pycba-tools) or PyniteFEA (through
pynite-tools), one load case at a time.

Both engines go through their tools package, which share one interface: the
model is written in the package's JSON schema (`model_dict`) and built with
its `load_dict`, reactions come from its `extract_node_reactions`, and curves
from the Pynite-shaped member view (`model.members["beam"].shear_array(...)`).
Results come back engine-neutral, as plain floats in SI base units (or the
scheme's own units when it uses plain numbers):

- reactions at each support for each load case: vertical force (up positive),
  moment (counter-clockwise positive) and horizontal force (right positive);
- curves along the beam for each load case: shear (positive where the left
  side is pushed up), moment (sagging positive), deflection (up positive) and
  rotation (counter-clockwise positive).

Loads without a `case` are analysed together as the "Factored" case.

Horizontal reactions come from statics: the horizontal components of angled
loads are carried by the first node that restrains horizontal movement (a pin,
fixed support or rotational spring). Rollers and vertical springs are free to
slide.

Requires the `pycba` or `pynite` extra:
`uv add "beamz9000[pycba]"` or `uv add "beamz9000[pynite]"`.
"""

from __future__ import annotations

import importlib.util
import math
from dataclasses import dataclass, field
from typing import Literal, Optional

import numpy as np

from beamz9000 import units
from beamz9000.scheme import Beam

FACTORED = "Factored"
MEMBER = "beam"

Engine = Literal["auto", "pycba", "pynite"]
Quantity = Literal["shear", "moment", "deflection", "rotation"]

# Sampling along the beam: evenly spaced stations plus stations either side of
# every point load, moment and support, so jumps are captured.
_STATIONS = 240
_EPS = 1e-6

_HORIZONTAL_RESTRAINTS = ("pin", "fixed", "rotational_spring")


@dataclass(frozen=True)
class Reaction:
    node: int
    case: str
    fy: float
    mz: float = 0.0
    fx: float = 0.0


@dataclass(frozen=True)
class Curve:
    quantity: Quantity
    case: str
    x: tuple[float, ...]
    y: tuple[float, ...]


@dataclass(frozen=True)
class AnalysisResult:
    engine: str
    cases: list[str]
    reactions: list[Reaction] = field(default_factory=list)
    curves: list[Curve] = field(default_factory=list)

    def curve(self, quantity: str, case: str) -> Curve:
        return next(c for c in self.curves if c.quantity == quantity and c.case == case)

    def reaction(self, node: int, case: str) -> Reaction:
        return next(r for r in self.reactions if r.node == node and r.case == case)


@dataclass(frozen=True)
class _Load:
    """A load in SI floats: downward forces and counter-clockwise moments positive."""

    kind: Literal["point", "moment", "line"]
    case: str
    x1: float
    mag1: float
    x2: float = 0.0
    mag2: float = 0.0
    angle: float = 0.0

    @property
    def vertical(self) -> float:
        return self.mag1 * math.cos(math.radians(self.angle))

    @property
    def horizontal(self) -> float:
        """Rightward component of an angled point load."""
        return self.mag1 * math.sin(math.radians(self.angle))


def available_engines() -> list[str]:
    """The engines that are installed, in order of preference."""
    found = []
    if importlib.util.find_spec("pycba_tools"):
        found.append("pycba")
    if importlib.util.find_spec("pynite_tools") and importlib.util.find_spec("Pynite"):
        found.append("pynite")
    return found


def resolve_engine(engine: Engine = "auto") -> str:
    """Returns the engine to use, or raises ImportError naming the extra to install."""
    installed = available_engines()
    if engine == "auto":
        if not installed:
            raise ImportError(
                "analysing a beam needs pycba-tools or pynite-tools; install one with "
                '`uv add "beamz9000[pycba]"` or `uv add "beamz9000[pynite]"`'
            )
        return installed[0]
    if engine not in installed:
        package = {"pycba": "pycba-tools", "pynite": "pynite-tools"}[engine]
        raise ImportError(f'the {engine} engine needs {package}; install it with `uv add "beamz9000[{engine}]"`')
    return engine


def analyze(beam: Beam, quantities: Optional[list[str]] = None, engine: Engine = "auto") -> AnalysisResult:
    """
    Analyses 'beam' for each of its load cases and returns the reactions and
    the curves for 'quantities' (any of shear, moment, deflection, rotation).

    The model is built through the engine's tools package: `model_dict`
    writes it in that package's JSON schema and the package's `load_dict`
    turns it into a model.

    Deflection and rotation need the beam's stiffness (`e` and `i`, or `ei`)
    and are left out without it. Without a stiffness, the beam is analysed
    with EI = 1, which gives the right forces for a prismatic beam on rigid
    supports; a spring with a stiffness then needs a real EI.
    """
    engine = resolve_engine(engine)
    inputs = _Inputs.of(beam)
    quantities = [q for q in (quantities or []) if inputs.has_stiffness or q not in ("deflection", "rotation")]
    if not inputs.cases:
        return AnalysisResult(engine=engine, cases=[])
    model = build_model(beam, engine)
    reactions = _reactions(model, inputs)
    curves = _curves(model, inputs, quantities)
    return AnalysisResult(engine=engine, cases=inputs.cases, reactions=reactions, curves=curves)


def build_model(beam: Beam, engine: Engine = "auto"):
    """
    Returns the analysed model of 'beam': a pycba-tools CBAModel or a Pynite
    FEModel3D, built with its tools package's `load_dict`. Each load case has
    a load combination of the same name.
    """
    engine = resolve_engine(engine)
    if engine == "pycba":
        import pycba_tools as tools
    else:
        import pynite_tools as tools
    model = tools.load_dict(model_dict(beam, engine))
    if engine == "pycba":
        model.analyze()
    else:
        model.analyze(check_statics=False)
    return model


def model_dict(beam: Beam, engine: Engine = "auto") -> dict:
    """
    Returns 'beam' as an analysis-ready model in the JSON schema of the
    engine's tools package (pycba-tools' CBAModel or pynite-tools'
    FEModel3D), ready for that package's `load_dict`, or to save with
    `json.dump` and share.
    """
    engine = resolve_engine(engine)
    inputs = _Inputs.of(beam)
    return _pycba_dict(inputs) if engine == "pycba" else _pynite_dict(inputs)


# --- Inputs ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Inputs:
    """A beam as plain floats, checked for analysis."""

    nodes: list[float]
    supports: list  # scheme Supports
    ei: float
    has_stiffness: bool
    loads: list[_Load]
    cases: list[str]

    @classmethod
    def of(cls, beam: Beam) -> "_Inputs":
        supports = beam.support_specs
        springs = [i for i, s in enumerate(supports) if s.type in ("spring", "rotational_spring")]
        for i in springs:
            if supports[i].k is None:
                raise ValueError(
                    f"the {supports[i].type.replace('_', ' ')} at node {i} needs a stiffness to analyse "
                    f"the beam, e.g. {{spring: 12 kN/mm}}"
                )
        ei = beam.stiffness
        if ei is None and springs:
            raise ValueError("a beam on springs needs its stiffness (`e` and `i`, or `ei`) to be analysed")
        loads = _loads(beam)
        return cls(
            nodes=[units.si(n) for n in beam.nodes],
            supports=supports,
            ei=units.si(ei) if ei is not None else 1.0,
            has_stiffness=ei is not None,
            loads=loads,
            cases=list(dict.fromkeys(l.case for l in loads)),
        )

    @property
    def names(self) -> list[str]:
        return [f"N{i}" for i in range(len(self.nodes))]

    @property
    def x_restraint(self) -> Optional[int]:
        """The node that carries horizontal load, if any."""
        restrained = [i for i, s in enumerate(self.supports) if s.type in _HORIZONTAL_RESTRAINTS]
        return restrained[0] if restrained else None


def _loads(beam: Beam) -> list[_Load]:
    out = []
    for r in beam.resolved_loads:
        case = r.case if r.case is not None else FACTORED
        if r.kind == "line":
            out.append(_Load("line", case, units.si(r.x1), units.si(r.mag1), units.si(r.x2), units.si(r.mag2)))
        else:
            out.append(_Load(r.kind, case, units.si(r.x1), units.si(r.mag1), angle=r.angle))
    return out


def _combos(cases: list[str]) -> dict:
    return {case: {"name": case, "factors": {case: 1.0}} for case in cases}


# --- pycba-tools schema ------------------------------------------------------------------


def _pycba_dict(inputs: _Inputs) -> dict:
    R = []
    for s in inputs.supports:
        k = units.si(s.k) if s.k is not None else None
        R += {
            "pin": [-1, 0],
            "roller": [-1, 0],
            "fixed": [-1, -1],
            "spring": [k, 0],  # pycba: a positive restraint is a spring stiffness.
            "rotational_spring": [-1, k],
            "free": [0, 0],
        }[s.type]
    nodes = inputs.nodes
    spans = [b - a for a, b in zip(nodes, nodes[1:])]
    cases: dict[str, list] = {case: [] for case in inputs.cases}
    for l in inputs.loads:
        cases[l.case] += _pycba_rows(l, nodes)
    return {
        "backend": "pycba",
        "name": MEMBER,
        "node_names": inputs.names,
        "node_locations": nodes,
        "L": spans,
        "EI": [inputs.ei] * len(spans),
        "R": R,
        "eletype": [1] * len(spans),
        "D": [None] * len(R),
        "load_cases": cases,
        "load_combos": _combos(inputs.cases),
    }


def _pycba_rows(l: _Load, nodes: list[float]) -> list[list[float]]:
    """pycba load matrix rows (1-based span numbers, span-local distances) for one load."""
    tol = 1e-9 * (nodes[-1] - nodes[0])
    if l.kind != "line":
        # On an internal node, the load goes on the end of the span to its left.
        span = next(i for i in range(len(nodes) - 1) if l.x1 <= nodes[i + 1] + tol)
        a = l.x1 - nodes[span]
        return [[span + 1, 2, l.vertical, a] if l.kind == "point" else [span + 1, 4, l.mag1, a]]
    rows = []
    for span, (s0, s1) in enumerate(zip(nodes, nodes[1:])):
        start, end = max(l.x1, s0), min(l.x2, s1)
        if end - start <= tol:
            continue
        wa, wb = (l.mag1 + (l.mag2 - l.mag1) * (x - l.x1) / (l.x2 - l.x1) for x in (start, end))
        a, c = start - s0, end - start
        full = abs(a) <= tol and abs(c - (s1 - s0)) <= tol
        if wa == wb:
            rows.append([span + 1, 1, wa] if full else [span + 1, 3, wa, a, c])
        else:
            rows.append([span + 1, 5, wa, wb] if full else [span + 1, 5, wa, wb, a, c])
    return rows


# --- pynite-tools schema -----------------------------------------------------------------


def _pynite_dict(inputs: _Inputs) -> dict:
    # EI as E with I = 1. Axial and out-of-plane stiffness only need to be finite.
    material = {"name": "material", "E": inputs.ei, "G": inputs.ei, "nu": 0.3, "rho": 0.0}
    section = {"name": "section", "A": 1.0, "Iy": 1.0, "Iz": 1.0, "J": 1.0}
    supported = [i for i, s in enumerate(inputs.supports) if s.type != "free"]
    x_node = inputs.x_restraint if inputs.x_restraint is not None else (supported or [0])[0]
    nodes = {}
    for i, (name, x, s) in enumerate(zip(inputs.names, inputs.nodes, inputs.supports)):
        node = {
            "name": name, "X": x, "Y": 0.0, "Z": 0.0,
            "support_DX": i == x_node,
            "support_DY": s.type in ("pin", "roller", "fixed", "rotational_spring"),
            "support_DZ": True, "support_RX": True, "support_RY": True,
            "support_RZ": s.type == "fixed",
        }
        if s.type == "spring":
            node["spring_DY"] = [units.si(s.k), None, True]
        elif s.type == "rotational_spring":
            node["spring_RZ"] = [units.si(s.k), None, True]
        nodes[name] = node
    pt_loads, dist_loads = [], []
    for l in inputs.loads:
        if l.kind == "point":
            pt_loads.append(["FY", -l.vertical, l.x1, l.case])
            if l.horizontal:
                pt_loads.append(["FX", l.horizontal, l.x1, l.case])
        elif l.kind == "moment":
            pt_loads.append(["MZ", l.mag1, l.x1, l.case])
        else:
            dist_loads.append(["FY", -l.mag1, -l.mag2, l.x1, l.x2, l.case, False])
    return {
        "nodes": nodes,
        "materials": {"material": material},
        "sections": {"section": section},
        "members": {
            MEMBER: {
                "name": MEMBER, "i_node": inputs.names[0], "j_node": inputs.names[-1],
                # Embedded rather than named: pynite-tools 0.8.1 cannot read a section given by name.
                "material": material, "section": section,
                "PtLoads": pt_loads, "DistLoads": dist_loads,
            }
        },
        "load_combos": _combos(inputs.cases),
    }


# --- Results --------------------------------------------------------------------------


def _reactions(model, inputs: _Inputs) -> list[Reaction]:
    """Each support's reactions per case, from the tools' `extract_node_reactions`."""
    module = type(model).__module__.split(".")[0]
    if module == "pycba_tools":
        import pycba_tools as tools
    else:
        import pynite_tools as tools
    tree = tools.extract_node_reactions(model, results_key=None)
    out = []
    for case in inputs.cases:
        fx_total = -sum(l.horizontal for l in inputs.loads if l.case == case and l.kind == "point")
        for i, (name, s) in enumerate(zip(inputs.names, inputs.supports)):
            if s.type == "free":
                continue
            node = tree.get(name, {})
            fy = float(node.get("FY", {}).get(case, 0.0))
            mz = float(node.get("MZ", {}).get(case, 0.0)) if s.type in ("fixed", "rotational_spring") else 0.0
            fx = fx_total if i == inputs.x_restraint else 0.0
            out.append(Reaction(i, case, _clean(fy), _clean(mz), _clean(fx)))
    return out


def _stations(nodes, loads) -> np.ndarray:
    L = nodes[-1] - nodes[0]
    xs = set(np.linspace(nodes[0], nodes[-1], _STATIONS).tolist())
    jumps = list(nodes) + [l.x1 for l in loads if l.kind != "line"]
    jumps += [x for l in loads if l.kind == "line" for x in (l.x1, l.x2)]
    for x in jumps:
        xs.update((x - _EPS * L, x + _EPS * L))
    return np.array(sorted(x for x in xs if nodes[0] <= x <= nodes[-1]))


def _curves(model, inputs: _Inputs, quantities) -> list[Curve]:
    """Curves along the beam, from the member view both tools packages share."""
    if not quantities:
        return []
    nodes, cases = inputs.nodes, inputs.cases
    member = model.members[MEMBER]
    xs = _stations(nodes, inputs.loads)
    local = xs - nodes[0]
    n = len(xs)
    out = []
    for case in cases:
        values = {}
        if "shear" in quantities:
            values["shear"] = member.shear_array("Fy", n, case, x_array=local)[1]
        if "moment" in quantities:
            # Pynite's Mz is negative in sagging; diagrams show sagging positive.
            values["moment"] = -member.moment_array("Mz", n, case, x_array=local)[1]
        if "deflection" in quantities:
            values["deflection"] = member.deflection_array("dy", n, case, x_array=local)[1]
        if "rotation" in quantities:
            # The slope of the deflected shape, from an even grid (the deflection
            # is smooth, so the paired stations at jumps only add noise).
            grid = np.linspace(local[0], local[-1], 4 * _STATIONS + 1)
            dy = member.deflection_array("dy", len(grid), case, x_array=grid)[1]
            values["rotation"] = np.interp(local, grid, np.gradient(dy, grid, edge_order=2))
        for q in quantities:
            if q in values:
                y = np.asarray(values[q], dtype=float)
                out.append(Curve(q, case, tuple(xs.tolist()), tuple(np.where(np.abs(y) < 1e-12, 0.0, y).tolist())))
    return out


def _clean(value: float) -> float:
    return 0.0 if abs(value) < 1e-9 else value
