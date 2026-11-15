"""Analysis with pycba-tools and pynite-tools: scheme forms, values, both engines, drawing."""

import json
import pathlib

import numpy as np
import pytest

import beamz9000 as bz
from beamz9000 import analysis
from beamz9000.graphics.elements import Shape, Text, flatten
from beamz9000.scheme import Results
from beamz9000.spec import from_scheme

EXAMPLES = pathlib.Path(__file__).parents[1] / "examples"
ENGINES = ["pycba", "pynite"]


def _beam(**fields):
    data = {"spans": ["6 m"], **fields}
    return bz.parse_scheme({"_environment": "structural", "B": data})["B"]


# --- Scheme --------------------------------------------------------------------------


@pytest.mark.parametrize("value, diagrams", [
    (["forces"], ["shear", "moment"]),
    (["forces", "deflections"], ["shear", "moment", "deflection"]),
    ("moment", ["moment"]),
    (["rotations", "shear", "forces"], ["rotation", "shear", "moment"]),
    ({"diagrams": ["deflection"], "engine": "pynite"}, ["deflection"]),
    ([{"diagrams": ["moment"]}], ["moment"]),
])
def test_results_forms(value, diagrams):
    assert Results.model_validate(value).diagrams == diagrams


def test_unknown_result_names_the_choices():
    with pytest.raises(ValueError, match="unknown result 'stress'.*forces"):
        Results.model_validate(["stress"])


def test_no_results_no_analysis():
    spec = from_scheme(_beam(loads=[{"dist": {"w": "5 kN/m", "case": "D"}}]))
    assert spec.reactions == [] and spec.diagrams == []


# --- Values ---------------------------------------------------------------------------


@pytest.mark.parametrize("engine", ENGINES)
def test_simply_supported_udl_matches_hand_values(engine):
    w, L, EI = 5e3, 6.0, 200e9 * 60e-6  # 5 kN/m, 6 m, 200 GPa x 60e6 mm4
    beam = _beam(e="200 GPa", i="60e6 mm**4", loads=[{"dist": {"w": "5 kN/m", "case": "D"}}])
    result = analysis.analyze(beam, ["shear", "moment", "deflection"], engine)
    assert result.engine == engine
    assert [r.fy for r in result.reactions] == pytest.approx([w * L / 2] * 2)
    moment = result.curve("moment", "D")
    assert max(moment.y) == pytest.approx(w * L**2 / 8, rel=1e-4)  # Sagging positive.
    shear = result.curve("shear", "D")
    assert shear.y[0] == pytest.approx(w * L / 2, rel=1e-3)  # Positive at the left end.
    deflection = result.curve("deflection", "D")
    assert min(deflection.y) == pytest.approx(-5 * w * L**4 / (384 * EI), rel=1e-4)


@pytest.mark.parametrize("engine", ENGINES)
def test_cantilever_reactions_include_moment_and_horizontal(engine):
    beam = _beam(spans=["3 m"], cantilever="right",
                 loads=[{"point": {"p": "10 kN", "loc": "L", "angle": 30, "case": "L"}}])
    (r,) = analysis.analyze(beam, [], engine).reactions
    assert r.fy == pytest.approx(10e3 * np.cos(np.radians(30)))
    assert r.mz == pytest.approx(3 * 10e3 * np.cos(np.radians(30)))  # Counter-clockwise.
    assert r.fx == pytest.approx(-5e3)  # The load leans right; the wall pushes left.


@pytest.mark.parametrize("beam_id", ["floor_beam", "cantilever", "on_springs"])
def test_engines_agree(beam_id):
    beam = bz.load_scheme(EXAMPLES / "analysis.yaml")[beam_id]
    kinds = ["shear", "moment", "deflection", "rotation"]
    a, b = (analysis.analyze(beam, kinds, e) for e in ENGINES)
    assert a.cases == b.cases
    for ra in a.reactions:
        rb = b.reaction(ra.node, ra.case)
        assert (rb.fy, rb.mz, rb.fx) == pytest.approx((ra.fy, ra.mz, ra.fx), abs=1e-6)
    for ca in a.curves:
        cb = b.curve(ca.quantity, ca.case)
        scale = max(abs(v) for v in ca.y)
        assert np.max(np.abs(np.subtract(ca.y, cb.y))) <= 2e-3 * scale


def test_uncased_loads_form_an_unnamed_case():
    beam = _beam(loads=[{"point": {"p": "10 kN", "x": "3 m"}}], results=["forces", "reactions"])
    result = analysis.analyze(beam, ["moment"])
    assert result.cases == [None]
    spec = from_scheme(beam)
    assert spec.keys == []  # No legend entry.
    assert {r.key for r in spec.reactions} == {None}
    assert spec.loads[0].key is None


@pytest.mark.parametrize("engine", ENGINES)
def test_model_dict_is_json_and_loads_with_the_tools(engine):
    beam = bz.load_scheme(EXAMPLES / "analysis.yaml")["on_springs"]
    data = json.loads(json.dumps(analysis.model_dict(beam, engine)))
    tools = pytest.importorskip("pycba_tools" if engine == "pycba" else "pynite_tools")
    model = tools.load_dict(data)
    assert set(model.load_combos) == {"D", "L"}


# --- Checks -----------------------------------------------------------------------------


def test_spring_without_stiffness_cannot_be_analysed():
    beam = _beam(spans=["3 m", "3 m"], supports=["pin", "spring", "roller"],
                 loads=[{"dist": {"w": "2 kN/m"}}])
    with pytest.raises(ValueError, match="spring at node 1 needs a stiffness"):
        analysis.analyze(beam)


def test_springs_need_ei():
    beam = _beam(spans=["3 m", "3 m"], supports=["pin", {"spring": "5 kN/mm"}, "roller"],
                 loads=[{"dist": {"w": "2 kN/m"}}])
    with pytest.raises(ValueError, match="needs its stiffness"):
        analysis.analyze(beam)


def test_deflection_needs_ei_and_is_skipped_without_it():
    with pytest.warns(UserWarning, match="need `e` and `i`"):
        beam = _beam(loads=[{"dist": {"w": "2 kN/m", "case": "D"}}], results=["forces", "deflections"])
    spec = from_scheme(beam)
    assert [d.kind for d in spec.diagrams] == ["shear", "moment"]


def test_missing_engine_warns_and_draws_without_results(monkeypatch):
    monkeypatch.setattr(analysis, "available_engines", lambda: [])
    beam = _beam(loads=[{"dist": {"w": "2 kN/m", "case": "D"}}], results=["forces"])
    with pytest.warns(UserWarning, match=r"needs pycba-tools.*beamz9000\[pycba\]"):
        spec = from_scheme(beam)
    assert spec.reactions == []


def test_pycba_is_the_default_engine():
    beam = _beam(loads=[{"dist": {"w": "2 kN/m", "case": "D"}}], results=["forces"])
    assert beam.results.engine == "pycba"
    assert analysis.analyze(beam).engine == "pycba"


def test_named_engine_must_be_installed(monkeypatch):
    monkeypatch.setattr(analysis, "available_engines", lambda: ["pynite"])
    with pytest.raises(ImportError, match=r"beamz9000\[pycba\]"):
        analysis.resolve_engine("pycba")
    assert analysis.resolve_engine("auto") == "pynite"


# --- Spec and drawing ----------------------------------------------------------------------


def test_spec_labels_use_the_schemes_units():
    spec = bz.as_spec(EXAMPLES / "analysis.yaml", "cantilever")
    labels = {r.key: r.label for r in spec.reactions}
    assert labels == {"D": "↑ 12 kN  ↺ 18 kN·m", "L": "↑ 8.66 kN  ← 5 kN  ↺ 26 kN·m"}
    moment = next(d for d in spec.diagrams if d.kind == "moment")
    assert {p.label for p in moment.peaks} == {"−18 kN·m", "−26 kN·m"}


def test_occupancy_cases_join_the_legend():
    spec = bz.as_spec(EXAMPLES / "analysis.yaml", "floor_beam")
    assert [k.name for k in spec.keys] == ["office", "L", "D"]
    assert {r.key for r in spec.reactions} == {"D", "L"}


def test_diagram_strata_with_results():
    diagram = bz.beam_diagram(EXAMPLES / "analysis.yaml", beam_id="floor_beam")
    roles = [c.role for c in diagram.children]
    assert roles == ["loads", "beam", "supports", "node_labels", "reactions", "dimensions", "results", "legend"]
    parts = {c.role: c for c in diagram.children}
    assert parts["reactions"].bounds[3] < parts["supports"].bounds[1]
    assert parts["dimensions"].bounds[3] < parts["reactions"].bounds[1]
    assert parts["results"].bounds[3] < parts["dimensions"].bounds[1]
    titles = [t.text for t in flatten(parts["results"]) if isinstance(t, Text) and t.ha == "right"]
    assert titles == ["Shear", "Moment", "Deflection"]


@pytest.mark.parametrize("tension_side, below", [(True, True), (False, False)])
def test_positive_moment_on_the_tension_side(tension_side, below):
    beam = _beam(loads=[{"dist": {"w": "5 kN/m", "case": "D"}}], results=["moment"])
    layout = bz.Layout(moment_on_tension_side=tension_side)
    panel = next(c for c in bz.beam_diagram(beam, layout).children if c.role == "results").children[0]
    axis_y = next(s for s in flatten(panel) if isinstance(s, Shape) and s.stroke_color == layout.ink).bounds[1]
    curve = next(s for s in flatten(panel) if isinstance(s, Shape) and s.key == "D" and s.fill_color is None)
    assert (curve.bounds[1] < axis_y) is below


def test_reaction_columns_do_not_overlap():
    diagram = bz.beam_diagram(EXAMPLES / "analysis.yaml", bz.Layout(font_size_pt=8),
                              beam_id="on_springs", width=500)
    texts = [t for t in flatten(next(c for c in diagram.children if c.role == "reactions"))]
    for i, a in enumerate(texts):
        for b in texts[i + 1:]:
            ax0, ay0, ax1, ay1 = a.bounds
            bx0, by0, bx1, by1 = b.bounds
            assert not (ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1), (a.text, b.text)


def test_analysed_beam_fits_an_exact_box():
    r = bz.SVGRenderer(width=600, height=600)
    diagram = bz.beam_diagram(EXAMPLES / "analysis.yaml", beam_id="floor_beam", aspect=r.aspect,
                              margin=r.margin, width=r.width_pt)
    x0, y0, x1, y1 = bz.render.frame(diagram.bounds, r.margin, r.aspect)
    assert (x1 - x0) / (y1 - y0) == pytest.approx(1.0)


# --- Load combinations ----------------------------------------------------------------------


def _combo_beam(**fields):
    return _beam(e="200 GPa", i="60e6 mm**4",
                 loads=[{"dist": {"w": "5 kN/m", "case": "D"}}, {"dist": {"w": "4 kN/m", "case": "L"}},
                        {"point": {"p": "100 kN", "x": "3 m"}}],  # Uncased: in no combination.
                 **fields)


@pytest.mark.parametrize("engine", ENGINES)
def test_force_combos_envelope_shear_moment_and_reactions(engine):
    beam = _combo_beam(load_combos=[{"ULS1": {"D": 1.4}}, {"ULS2": {"D": 1.25, "L": 1.5}}, {"W": {"W": 1.4}}],
                       results=["forces", "deflections", "reactions"])
    result = analysis.analyze(beam, ["shear", "moment", "deflection"], engine)
    assert result.cases == ["D", "L"]  # The uncased load is left out.
    assert result.combos == {"forces": ["ULS1", "ULS2"], "deflections": ["ULS1", "ULS2"]}  # W: no wind loads.
    w_max, w_min, L = 1.25 * 5e3 + 1.5 * 4e3, 1.4 * 5e3, 6.0
    moment = result.envelope("moment")
    assert max(moment.max) == pytest.approx(w_max * L**2 / 8, rel=1e-4)
    assert max(moment.min) == pytest.approx(w_min * L**2 / 8, rel=1e-4)
    (left, right) = result.reaction_envelopes()
    assert left.fy == pytest.approx((w_max * L / 2, w_min * L / 2))


def test_combo_groups_apply_separately():
    beam = _combo_beam(load_combos={"forces": [{"ULS": {"D": 1.25, "L": 1.5}}]},
                       results=["forces", "deflections"])
    result = analysis.analyze(beam, ["moment", "deflection"])
    assert result.envelope("moment") is not None
    assert result.envelope("deflection") is None  # No deflection combinations: the cases.
    assert {c.case for c in result.curves if c.quantity == "deflection"} == {"D", "L"}


def test_envelope_diagrams_and_factored_reactions_in_the_spec():
    spec = bz.as_spec(EXAMPLES / "analysis.yaml", "factored_floor_beam")
    kinds = {d.kind: d for d in spec.diagrams}
    assert kinds["moment"].envelope and kinds["moment"].title == "Moment envelope"
    assert [c.role for c in kinds["moment"].curves] == ["max", "min"]
    assert kinds["deflection"].envelope  # Over the SLS combination.
    node_a = [r for r in spec.reactions if r.node == 0]
    assert [(r.key, r.role) for r in node_a] == [("D", "case"), ("L", "case"), (None, "max"), (None, "min")]
    assert node_a[2].label.startswith("max ↑ ") and node_a[3].label.startswith("min ↑ ")


def test_reactions_are_opt_in():
    beam = _beam(loads=[{"dist": {"w": "5 kN/m", "case": "D"}}], results=["moment"])
    assert from_scheme(beam).reactions == []
    alone = _beam(loads=[{"dist": {"w": "5 kN/m", "case": "D"}}], results=["reactions"])
    assert alone.results.requested and alone.results.diagrams == []
    spec = from_scheme(alone)
    assert [r.label for r in spec.reactions] == ["↑ 15 kN", "↑ 15 kN"] and spec.diagrams == []
    mapping = _beam(loads=[{"dist": {"w": "5 kN/m", "case": "D"}}],
                    results={"diagrams": ["shear", "reactions"], "engine": "pycba"})
    assert mapping.results.reactions and mapping.results.diagrams == ["shear"]


def test_combo_named_like_a_case_is_an_error():
    beam = _combo_beam(load_combos=[{"D": {"D": 1.4}}], results=["moment"])
    with pytest.raises(ValueError, match="'D' has the name of a load case"):
        analysis.analyze(beam, ["moment"])


def test_engines_agree_on_envelopes():
    beam = bz.load_scheme(EXAMPLES / "analysis.yaml")["factored_floor_beam"]
    a, b = (analysis.analyze(beam, ["shear", "moment", "deflection"], e) for e in ENGINES)
    for q in ("shear", "moment", "deflection"):
        ea, eb = a.envelope(q), b.envelope(q)
        scale = max(map(abs, ea.max + ea.min))
        assert np.max(np.abs(np.subtract(ea.max, eb.max))) <= 2e-3 * scale
        assert np.max(np.abs(np.subtract(ea.min, eb.min))) <= 2e-3 * scale
    for ra, rb in zip(a.reaction_envelopes(), b.reaction_envelopes()):
        assert ra.fy == pytest.approx(rb.fy, abs=1e-6)
