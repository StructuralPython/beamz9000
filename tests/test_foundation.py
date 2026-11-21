"""Beams on an elastic foundation: the scheme, both engines, the pressure diagram and the drawing."""

import json
import warnings

import numpy as np
import pytest

import beamz9000 as bz
from beamz9000 import analysis
from beamz9000.graphics.elements import Text, flatten
from beamz9000.results import results_dict

ENGINES = ["pycba", "pynite"]
LOADS = [
    {"point": {"p": "400 kN", "loc": "1200 mm", "case": "D"}},
    {"dist": {"mag1": "10 kN/m", "mag2": "30 kN/m", "x1": "2000 mm", "x2": "6000 mm", "case": "D"}},
]
TOTAL = 480e3  # N


def footing(foundation=None, **fields):
    """A 6 m, 500 x 600 strip footing on 5 MPa/m soil (compression only unless 'foundation' says)."""
    data = {
        "spans": ["6000 mm"], "e": "25 GPa", "i": "9000e6 mm**4", "depth": "600 mm",
        "foundation": foundation or {"ks": [None, "5 MPa/m"], "width": "500 mm"},
        "loads": LOADS, **fields,
    }
    return bz.parse_scheme({"_environment": "structural", "F": data})["F"]


def soil_load(curve, width=0.5):
    """The load the soil carries, from a pressure curve."""
    return np.trapezoid(curve.y, curve.x) * width


# --- Scheme ---------------------------------------------------------------------


@pytest.mark.parametrize("foundation, label", [
    ({"ks": [None, "5 MPa/m"], "width": "500 mm"}, "ks = 5 MPa/m, compression only"),
    ({"ks": "5 MPa/m", "width": "500 mm"}, "ks = 5 MPa/m"),
    ({"ks": ["-5 MPa/m", "5 MPa/m"], "width": "500 mm"}, "ks = 5 MPa/m"),
    ({"ks": ["-2 MPa/m", "5 MPa/m"], "width": "500 mm"}, "ks = 5 MPa/m in compression, 2 MPa/m in tension"),
    ({"kf": [None, "2.5 MN/m**2"]}, "kf = 2.5 MN/m², compression only"),
])
def test_foundation_forms(foundation, label):
    beam = footing(foundation)
    assert beam.foundation.label == label
    tension, compression = (float(getattr(v, "value", v)) for v in beam.foundation.moduli)
    assert compression == pytest.approx(2.5e6)  # ks x width, or kf


def test_nodes_are_free_on_a_foundation():
    assert footing(spans=["3000 mm", "3000 mm"]).node_supports == ["free", "free", "free"]
    assert footing(spans=["3000 mm", "3000 mm"], supports={1: "pin"}).node_supports == ["free", "pin", "free"]


def test_a_foundation_counts_as_support():
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # No "do not make a stable beam" warning.
        footing()


@pytest.mark.parametrize("foundation, message", [
    ({"ks": [None, "5 MPa/m"]}, "needs the beam's `width`"),
    ({"ks": ["5 MPa/m", "5 MPa/m"], "width": "500 mm"}, "as negative"),
    ({"ks": [None, None], "width": "500 mm"}, "must be positive"),
    ({"ks": [None, "5 MPa/m"], "kf": [None, "2.5 MPa"], "width": "500 mm"}, "not both"),
    ({"ks": [None, "5 MPa"], "width": "500 mm"}, "subgrade modulus"),
    ({"kf": [None, "5 MPa/m"]}, "foundation modulus"),
    ({"ks": [None, "5 MPa/m", "6 MPa/m"], "width": "500 mm"}, "got 3 values"),
])
def test_invalid_foundations(foundation, message):
    with pytest.raises(ValueError, match=message):
        footing(foundation)


def test_pressure_needs_a_foundation():
    with pytest.raises(ValueError, match="`pressure` diagram"):
        bz.parse_scheme({"B": {"spans": [6], "results": ["pressure"]}})


def test_plain_numbers():
    beam = bz.parse_scheme({"B": {
        "spans": [6.0], "ei": 225e6, "foundation": {"kf": [None, 2.5e6]},
        "loads": [{"point": {"p": 100e3, "loc": 1.0, "case": "D"}}],
    }})["B"]
    result = analysis.analyze(beam, ["pressure"])
    assert np.trapezoid(result.curve("pressure", "D").y, result.curve("pressure", "D").x) == pytest.approx(100e3, rel=1e-4)


# --- Analysis --------------------------------------------------------------------


@pytest.mark.parametrize("engine", ENGINES)
def test_compression_only_lifts_off(engine):
    result = analysis.analyze(footing(), ["pressure", "deflection"], engine)
    p, d = result.curve("pressure", "D"), result.curve("deflection", "D")
    assert soil_load(p) == pytest.approx(TOTAL, rel=1e-3)
    assert min(p.y) >= -1e-6 * max(p.y)  # Never pulls the footing down...
    assert p.y[-1] == pytest.approx(0.0, abs=1e-6) and d.y[-1] > 0.011  # ...and the far end lifts.
    assert max(p.y) == pytest.approx(371.1e3, rel=2e-3)


@pytest.mark.parametrize("engine", ENGINES)
def test_a_linear_foundation_holds_the_end_down(engine):
    result = analysis.analyze(footing({"ks": "5 MPa/m", "width": "500 mm"}), ["pressure"], engine)
    p = result.curve("pressure", "D")
    assert min(p.y) == pytest.approx(-42.5e3, rel=5e-3)  # Tension at the far end.
    assert soil_load(p) == pytest.approx(TOTAL, rel=1e-3)


@pytest.mark.parametrize("foundation", [
    {"ks": [None, "5 MPa/m"], "width": "500 mm"},
    {"ks": "5 MPa/m", "width": "500 mm"},
])
@pytest.mark.parametrize("supports", [None, ["pin", "free"]])
def test_engines_agree(foundation, supports):
    fields = {"supports": supports} if supports else {}
    kinds = ["shear", "moment", "deflection", "pressure"]
    a, b = (analysis.analyze(footing(foundation, **fields), kinds, e) for e in ENGINES)
    for kind in kinds:
        ya, yb = np.array(a.curve(kind, "D").y), np.array(b.curve(kind, "D").y)
        assert np.abs(ya - yb).max() <= 5e-3 * np.abs(ya).max(), kind
    for ra in a.reactions:
        assert b.reaction(ra.node, "D").fy == pytest.approx(ra.fy, rel=1e-3)


@pytest.mark.parametrize("engine", ENGINES)
def test_supports_and_soil_share_the_load(engine):
    result = analysis.analyze(footing(supports=["pin", "free"]), ["pressure"], engine)
    support = result.reaction(0, "D").fy
    assert support > 0
    assert support + soil_load(result.curve("pressure", "D")) == pytest.approx(TOTAL, rel=1e-3)


@pytest.mark.parametrize("engine", ENGINES)
def test_free_ends_carry_no_shear(engine):
    shear = analysis.analyze(footing(), ["shear"], engine).curve("shear", "D")
    assert abs(shear.y[0]) < 1e-3 * TOTAL and abs(shear.y[-1]) < 1e-3 * TOTAL


def test_unequal_moduli_need_pycba():
    beam = footing({"ks": ["-2 MPa/m", "5 MPa/m"], "width": "500 mm"})
    assert analysis.analyze(beam, ["pressure"], "auto").engine == "pycba"
    with pytest.raises(ValueError, match="needs the pycba engine"):
        analysis.analyze(beam, ["pressure"], "pynite")
    lift = {kind: analysis.analyze(footing(f), ["deflection"]).curve("deflection", "D").y[-1]
            for kind, f in (("linear", {"ks": "5 MPa/m", "width": "500 mm"}),
                            ("bilinear", {"ks": ["-2 MPa/m", "5 MPa/m"], "width": "500 mm"}),
                            ("compression", None))}
    assert lift["linear"] < lift["bilinear"] < lift["compression"]


def test_a_foundation_needs_stiffness():
    beam = bz.parse_scheme({"_environment": "structural", "B": {
        "spans": ["6 m"], "foundation": {"kf": [None, "2.5 MN/m**2"]}, "loads": LOADS[:1],
    }})["B"]
    with pytest.raises(ValueError, match="needs its stiffness"):
        analysis.analyze(beam, ["pressure"])


@pytest.mark.parametrize("engine", ENGINES)
def test_model_dict(engine):
    data = json.loads(json.dumps(analysis.model_dict(footing(), engine)))
    if engine == "pycba":
        assert data["kf"] == [pytest.approx(2.5e6)] and data["kf_tension"] == [0.0]
    else:
        springs = [n for n in data["nodes"].values() if n["spring_DY"][0] is not None]
        assert len(springs) > 40 and all(n["spring_DY"][1] == "-" for n in springs)


def test_combinations_are_analysed_on_their_own():
    beam = footing(
        loads=[{"point": {"p": "200 kN", "loc": "500 mm", "case": "D"}},
               {"point": {"p": "200 kN", "loc": "5500 mm", "case": "L"}}],
        load_combos=[{"C1": {"D": 1.0}}, {"C2": {"D": 1.0, "L": 1.0}}],
    )
    result = analysis.analyze(beam, ["pressure"])
    assert result.curve("pressure", "C1").y[-1] == pytest.approx(0.0, abs=1.0)  # D alone lifts the far end...
    assert result.curve("pressure", "C2").y[-1] > 1e4  # ...D + L presses it down.


# --- Spec, drawing and results ---------------------------------------------------------


def test_pressure_diagram_and_units():
    spec = bz.spec.from_scheme(footing(results=["pressure"]))
    (diagram,) = spec.diagrams
    assert diagram.title == "Soil pressure"
    assert [p.label for p in diagram.peaks] == ["371 kPa", "0 kPa"]


def test_without_a_width_the_reaction_is_per_length():
    spec = bz.spec.from_scheme(footing({"kf": [None, "2.5 MN/m**2"]}, results=["pressure"]))
    (diagram,) = spec.diagrams
    assert diagram.title == "Foundation reaction"
    assert diagram.peaks[0].label == "186 kN/m"


def test_the_foundation_is_drawn():
    d = bz.beam_diagram(footing(results=["pressure"], node_labels="auto"))
    roles = [c.role for c in d.children]
    assert roles.index("foundation") < roles.index("supports")
    assert "ks = 5 MPa/m, compression only" in [t.text for t in flatten(d) if isinstance(t, Text)]
    soil = next(c for c in d.children if c.role == "foundation")
    labels = next(c for c in d.children if c.role == "node_labels")
    assert labels.bounds[3] <= soil.bounds[1]  # Node labels under the foundation's ground.
    # Soil pressure is drawn below its axis, like the pressure block under a footing.
    panel = next(c for c in d.children if c.role == "results").children[0]
    assert panel.key == "pressure"


def test_a_supported_node_takes_the_place_of_springs():
    def coils(beam):
        soil = next(c for c in bz.beam_diagram(beam).children if c.role == "foundation")
        return len(soil.children[0].geometry.geoms)

    assert coils(footing(supports={0: "pin"})) < coils(footing())


def test_results_dict_has_the_pressure():
    beam = footing(results=["pressure"])
    out = results_dict(beam, analysis.analyze(beam, ["pressure"]))
    assert out["units"]["pressure"] == "kPa"
    assert out["pressure"]["D"]["max"] == pytest.approx(371.1, rel=2e-3)
