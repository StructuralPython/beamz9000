"""
A beam's analysis results as a plain dict, in the units its scheme uses, for
reports and templates (the ymprint `_beam` block puts it in the document's
variables under the beam's name)::

    {
      "engine": "pycba",
      "units": {"force": "kN", "moment": "kN·m", "deflection": "mm", "rotation": "rad", "x": "m"},
      "cases": ["D", "L"],
      "combos": {"forces": ["ULS1", "ULS2"], "deflections": ["SLS"]},
      "reactions": {"A": {"D": {"Fy": 9.6, "Mz": 0.0, "Fx": 0.0}, ..., "max": {...}, "min": {...}}},
      "moment": {"ULS1": {"max": 21.5, "x_max": 4.2, "min": -12.6, "x_min": 1.6}, ...,
                 "envelope": {...}},
      "model": <the analysed CBAModel or FEModel3D>
    }

- `units` is None for a scheme in plain numbers; the values are then in its
  own consistent units.
- Supports are keyed by their node label, or `N0`, `N1`, ... without one.
  Loads without a case are under `uncased`.
- Each result asked for under `results` (shear, moment, deflection, rotation)
  lists each load case, or, when its group has load combinations, each
  combination plus their `envelope`. Reactions list each case, each force
  combination, and their `max` and `min`.
- Everything but `model` is plain numbers, strings, lists and dicts.
"""

from __future__ import annotations

from typing import Optional

from beamz9000 import units
from beamz9000.analysis import AnalysisResult
from beamz9000.scheme import Beam

UNCASED_KEY = "uncased"
QUANTITIES = ("shear", "moment", "deflection", "rotation")
_KIND = {"shear": "force", "moment": "moment", "deflection": "length", "rotation": "rotation"}


def results_dict(beam: Beam, result: AnalysisResult) -> dict:
    """Returns 'result', the analysis of 'beam', as a plain dict in the scheme's units (see the module)."""
    from beamz9000.spec import _result_units

    shown = _result_units(beam)
    x_unit = units.unit_of(beam.spans[0]) if shown is not None else None
    if x_unit not in units.RESULT_UNITS["length"]:
        x_unit = None if shown is None else "m"

    def value(v: float, kind: str) -> float:
        unit = None if shown is None or kind == "rotation" else shown[kind]
        factor = units.RESULT_UNITS.get(kind, {}).get(unit, 1.0) if unit else 1.0
        return _tidy(v / factor)

    def x(v: float) -> float:
        return _tidy(v / units.RESULT_UNITS["length"][x_unit]) if x_unit else _tidy(v)

    labels = beam.labels or []
    node_key = lambda i: (labels[i] if i < len(labels) and labels[i] else f"N{i}")
    reactions: dict[str, dict] = {}
    for r in result.reactions:
        reactions.setdefault(node_key(r.node), {})[_key(r.case)] = {
            "Fy": value(r.fy, "force"), "Mz": value(r.mz, "moment"), "Fx": value(r.fx, "force"),
        }
    for env in result.reaction_envelopes():
        node = reactions.setdefault(node_key(env.node), {})
        for i, role in enumerate(("max", "min")):
            node[role] = {"Fy": value(env.fy[i], "force"), "Mz": value(env.mz[i], "moment"),
                          "Fx": value(env.fx[i], "force")}

    out = {
        "engine": result.engine,
        "units": None if shown is None else {
            "force": shown["force"], "moment": shown["moment"], "deflection": shown["length"],
            "rotation": "rad", "x": x_unit,
        },
        "cases": [_key(c) for c in result.cases],
        "combos": {group: list(names) for group, names in result.combos.items()},
        "reactions": reactions,
    }
    for q in QUANTITIES:
        curves = [c for c in result.curves if c.quantity == q]
        if not curves:
            continue
        entry = {}
        for c in curves:
            entry[_key(c.case)] = _extremes(c.x, c.y, lambda v: value(v, _KIND[q]), x)
        envelope = result.envelope(q)
        if envelope is not None:
            hi = _extremes(envelope.x, envelope.max, lambda v: value(v, _KIND[q]), x)
            lo = _extremes(envelope.x, envelope.min, lambda v: value(v, _KIND[q]), x)
            entry["envelope"] = {"max": hi["max"], "x_max": hi["x_max"], "min": lo["min"], "x_min": lo["x_min"]}
        out[q] = entry
    out["model"] = result.model
    return out


def _key(case: Optional[str]) -> str:
    return UNCASED_KEY if case is None else case


def _extremes(xs, ys, value, x) -> dict:
    i_max = max(range(len(ys)), key=lambda j: ys[j])
    i_min = min(range(len(ys)), key=lambda j: ys[j])
    return {"max": value(ys[i_max]), "x_max": x(xs[i_max]), "min": value(ys[i_min]), "x_min": x(xs[i_min])}


def _tidy(v: float) -> float:
    """'v' to 6 significant figures, with round-off and -0 as 0."""
    v = float(f"{v:.6g}")
    return 0.0 if abs(v) < 1e-12 else v
