import pathlib
import warnings

import pytest
from pydantic import ValidationError

from beamz9000 import units
from beamz9000.scheme import Beam, load_scheme, parse_scheme

EXAMPLE = pathlib.Path(__file__).parents[1] / "examples" / "beam_scheme.yaml"


def beam(**kw) -> Beam:
    kw.setdefault("spans", [4000, 3000])
    return Beam.model_validate(kw)


def test_example_resolves():
    b = load_scheme(EXAMPLE)["B1"]
    assert units.si(b.length) == pytest.approx(7.0)
    assert b.node_supports == ["pin", "roller", "free"]
    xs = [(r.kind, round(units.si(r.x1), 6)) for r in b.resolved_loads]
    assert xs == [
        ("point", 5.75), ("point", 6.5), ("line", 0.0), ("line", 1.0),
        ("line", 4.5), ("line", 4.5), ("moment", 0.0),
    ]
    assert b.load_combos == {"ULS1": {"D": 1.4}, "ULS2": {"D": 1.25, "L": 1.5}}
    assert b.results.diagrams == ["moment", "shear", "deflection"]
    assert units.si(b.stiffness) == pytest.approx(200e9 * 300e-6)


def test_occupancy_expands_per_case():
    b = load_scheme(EXAMPLE)["B1"]
    occ = [r for r in b.resolved_loads if r.occupancy == "residential"]
    assert [r.case for r in occ] == ["D", "L"]
    assert units.si(occ[0].mag1) == pytest.approx(1500 * 3)
    assert units.si(occ[1].mag2) == pytest.approx(1900 * 1.5)


def test_plain_numbers_and_aliases():
    b = beam(loads=[
        {"point": {"p": 10, "x": -500}},
        {"point": {"magnitude": 5, "span_loc": 0}},
        {"point": {"mag": 5, "loc": "L"}},
        {"dist": {"w": 2}},
        {"dist": {"mag1": 1, "mag2": 3, "span_loc1": [1, -1000], "x2": 7000}},
        {"pressure": {"q": 2, "trib": 3, "span_loc1": [1, 0]}},
    ])
    r = b.resolved_loads
    assert [r[i].x1 for i in range(3)] == [6500, 4000, 7000]
    assert (r[3].x1, r[3].x2, r[3].mag1, r[3].mag2) == (0, 7000, 2, 2)
    assert (r[4].x1, r[4].x2) == (6000, 7000)
    assert (r[5].x1, r[5].x2, r[5].mag1) == (4000, 7000, 6)


def test_flat_load_form():
    b = beam(loads=[{"type": "moment", "m": 3, "loc": 0}])
    assert b.resolved_loads[0].kind == "moment"


@pytest.mark.parametrize(
    "kw, supports",
    [
        ({"spans": [5000]}, ["pin", "roller"]),
        ({"spans": [5000], "cantilever": "right"}, ["fixed", "free"]),
        ({"spans": [5000], "cantilever": "left"}, ["free", "fixed"]),
        ({"spans": [1, 4, 1], "cantilever": "both"}, ["free", "pin", "roller", "free"]),
        ({"spans": [1, 4], "cantilever": "left"}, ["free", "pin", "roller"]),
        ({"spans": [4, 4], "supports": {0: "fixed"}}, ["fixed", "roller", "roller"]),
        ({"spans": [4, 4], "supports": ["fixed", "roller", "free"]}, ["fixed", "roller", "free"]),
    ],
)
def test_supports(kw, supports):
    assert Beam.model_validate(kw).node_supports == supports


@pytest.mark.parametrize(
    "kw, message",
    [
        ({"loads": [{"point": {"p": 1}}]}, "exactly one of `loc`"),
        ({"loads": [{"point": {"p": 1, "loc": 8000}}]}, "off the beam"),
        ({"loads": [{"point": {"p": 1, "span_loc": [2, 0]}}]}, "out of range"),
        ({"loads": [{"point": {"p": 1, "span_loc": [0, 4500]}}]}, "beyond the end of span 0"),
        ({"loads": [{"dist": {"w": 1, "x1": 3000, "x2": 1000}}]}, "end after it starts"),
        ({"loads": [{"dist": {"w": 1, "mag1": 2}}]}, "not both"),
        ({"loads": [{"pressure": {"mag": "office", "trib": 1}}]}, "occupancy 'office'"),
        ({"loads": [{"point": {"p": "5 kN", "loc": 0}}]}, "_environment"),
        ({"spans": [4000, -1]}, "must be positive"),
        ({"e": 200000}, "must be given together"),
        ({"supports": ["pin", "roller"]}, "3 nodes"),
        ({"cantilever": "both"}, "at least 3 spans"),
        ({"cantilever": "right", "supports": ["pin", "roller", "roller"]}, "conflicts"),
        ({"loads": [{"slab": {"mag": 1}}]}, "slab"),
    ],
)
def test_errors(kw, message):
    with pytest.raises(ValidationError, match=message):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            beam(**kw)


def test_mixed_units_rejected():
    with pytest.raises(ValidationError, match="mixes quantities"):
        parse_scheme({"_environment": "structural", "B": {"spans": ["4 m", 3000]}})


def test_wrong_dimension_rejected():
    with pytest.raises(ValidationError, match="force"):
        parse_scheme({"_environment": "structural",
                      "B": {"spans": ["4 m"], "loads": [{"point": {"p": "5 kN/m", "loc": "1 m"}}]}})


def test_deflection_without_stiffness_warns():
    with pytest.warns(UserWarning, match="skipped"):
        beam(results=[{"diagrams": ["deflection"]}])


def test_unstable_supports_warn():
    with pytest.warns(UserWarning, match="stable"):
        beam(supports=["roller", "roller", "roller"])


def test_combo_forms():
    b = beam(load_combos={"A": {"name": "D", "factor": 1.4},
                          "B": [{"name": "D", "factor": 1.2}, {"name": "L", "factor": 1.6}],
                          "C": {"D": 1.0}})
    assert b.load_combos == {"A": {"D": 1.4}, "B": {"D": 1.2, "L": 1.6}, "C": {"D": 1.0}}


def test_yaml_text_and_placeholders():
    s = load_scheme("B2:\n  spans: [3000]\n  e: ...\n  i: ...\n  supports:\n")
    assert s["B2"].stiffness is None


def test_quantities_keep_their_written_units():
    from beamz9000 import units
    from beamz9000.spec import from_scheme

    scheme = load_scheme("""
_environment: structural
B:
  spans: [4.5 m, 2500 mm]
  supports: [pin, {spring: 12 kN/mm}, roller]
  loads:
    - point: {p: -8 kN, loc: 1 m}
    - moment: {m: 5 kN*m, loc: 0 mm}
""")
    beam = scheme["B"]
    assert isinstance(beam.spans[0], units.Quantity)
    assert units.si(beam.spans[0]) == 4.5
    spec = from_scheme(beam)
    assert spec.span_labels == ["4.5 m", "2500 mm"]
    assert spec.support_labels[1] == "12 kN/mm"
    assert [l.label1 for l in spec.loads] == ["8 kN", "5 kN·m"]
    # Computed values have no source and fall back to forallpeople's units.
    assert spec.length_label == "7 m"


def test_typeset_units():
    from beamz9000.units import _typeset

    assert _typeset("300e6 mm**4") == "300e6 mm⁴"
    assert _typeset("5 kN * m") == "5 kN·m"
    assert _typeset("2 m**-1") == "2 m⁻¹"
