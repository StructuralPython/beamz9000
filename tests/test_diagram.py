import pathlib
import xml.etree.ElementTree as ET

import pytest

import beamz9000 as bz
from beamz9000.diagram.compose import load_bands, pack_rows
from beamz9000.graphics.elements import Group, Text, flatten
from beamz9000.spec import from_scheme

EXAMPLE = pathlib.Path(__file__).parents[1] / "examples" / "beam_scheme.yaml"


@pytest.fixture(scope="module")
def spec():
    # The free-body diagram only; tests/test_analysis.py covers the results.
    return from_scheme(bz.load_scheme(EXAMPLE)["B1"], "B1", analyze=False)


@pytest.fixture(scope="module")
def diagram(spec):
    return bz.beam_diagram(spec)


def test_spec_matches_scheme(spec):
    assert spec.nodes == [0.0, 4.5, 7.0]
    assert [k.name for k in spec.keys] == ["L", "D", "residential"]  # Uncased loads: no entry.
    occ = [l for l in spec.loads if l.key == "residential"][0]
    # Labelled with the trib width at each end; the pressures go in the legend.
    assert (occ.mag1, occ.mag2, occ.label1, occ.label2, occ.area_load) == (10200.0, 5100.0, "3 m", "1.5 m", True)
    assert spec.keys[-1].text == "residential (D 1.5 kPa, L 1.9 kPa)"
    varying = [l for l in spec.loads if l.label2 and l.key != "residential"][0]
    assert (varying.label1, varying.label2) == ("1 kN/m", "4 kN/m")


def test_split_occupancies():
    spec = from_scheme(bz.load_scheme(EXAMPLE)["B1"], split_occupancies=True)
    assert "residential" not in [k.name for k in spec.keys]
    assert len([l for l in spec.loads if l.area_load]) == 2


def test_pack_rows():
    assert pack_rows([(0, 1), (0.5, 1.5), (2, 3), (1.2, 1.4), (0.9, 2.1)], gap=0.1) == [0, 1, 0, 0, 2]
    assert pack_rows([(0, 1), (1.05, 2)], gap=0.1) == [0, 1]


def test_strata_order(diagram):
    loads, beam, supports, labels, dims, legend = diagram.children
    assert [c.role for c in diagram.children] == [
        "loads", "beam", "supports", "node_labels", "dimensions", "legend"]
    assert loads.bounds[1] > 0  # Loads sit above the beam,
    assert supports.bounds[3] <= 1e-9  # supports below it,
    assert dims.bounds[3] < supports.bounds[1]  # dimensions below the supports,
    assert legend.bounds[0] > max(loads.bounds[2], dims.bounds[2])  # legend to the right.


def test_bands_stack_in_key_order_without_overlap(spec, diagram):
    bands = diagram.children[0].children
    assert [b.key for b in bands] == ["L", None, "D", "residential"]
    for lower, upper in zip(bands, bands[1:]):
        assert upper.bounds[1] > lower.bounds[3]
    for band in bands:
        items = band.children
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                ax0, ay0, ax1, ay1 = a.bounds
                bx0, by0, bx1, by1 = b.bounds
                assert ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0


def test_overlapping_loads_move_up_a_row():
    beam = bz.Beam.model_validate({"spans": [10000], "loads": [
        {"point": {"p": 25, "loc": 2000, "case": "L"}},
        {"point": {"p": 25, "loc": 2150, "case": "L"}},
        {"dist": {"w": 3, "x1": 3000, "x2": 8000, "case": "L"}},
    ]})
    band = load_bands(from_scheme(beam), bz.Layout()).children[0]
    bases = sorted({round(item.bounds[1], 6) for item in band.children})
    assert len(bases) == 2


def test_cantilever_fixed_wall_faces_beam():
    d = bz.beam_diagram(bz.Beam.model_validate({"spans": [3000], "cantilever": "right",
                                                "loads": [{"point": {"p": 5, "loc": "L"}}]}))
    wall = d.children[2].children[0]
    assert wall.bounds[2] == pytest.approx(0.0, abs=1e-9)  # Entirely left of the fixed end.


def test_upward_point_load_points_up():
    d = bz.beam_diagram(bz.Beam.model_validate({"spans": [3000], "loads": [{"point": {"p": -5, "loc": 1500}}]}))
    item = d.children[0].children[0].children[0]
    shaft, head = item.children[0], item.children[1]
    assert head.bounds[3] > shaft.bounds[3] - 1e-9


def test_diagram_round_trips(diagram):
    assert Group.model_validate_json(diagram.model_dump_json()) == diagram


def test_every_label_is_text(diagram):
    texts = [l.text for l in flatten(diagram) if isinstance(l, Text)]
    for expected in ["15 kN", "10 kN", "2.5 kN/m", "1 kN/m", "4 kN/m", "3 m", "1.5 m", "5 kN·m",
                     "4500 mm", "2500 mm", "7000 mm", "Load cases & occupancies",
                     "residential (D 1.5 kPa, L 1.9 kPa)"]:
        assert expected in texts


def test_plain_number_scheme_draws():
    d = bz.beam_diagram(bz.load_scheme("B:\n  spans: [6, 4]\n  loads:\n    - dist: {w: 2}\n"))
    assert "2" in [t.text for t in flatten(d) if isinstance(t, Text)]
    legend = next(c for c in d.children if c.role == "legend")
    assert len(legend) == 0  # An uncased load has no legend entry.
    band = next(c for c in d.children if c.role == "loads").children[0]
    assert band.key is None and all(s.stroke_color in (None, "black") for s in flatten(band) if hasattr(s, "stroke_color"))


def test_renderers(tmp_path, diagram):
    png = bz.draw(diagram, tmp_path / "b.png")
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    pdf = bz.draw(diagram, tmp_path / "b.pdf")
    assert b"/FontFile2" in pdf.read_bytes()  # TrueType embedded: text stays text.
    svg = bz.draw(diagram, tmp_path / "b.svg")
    root = ET.parse(svg).getroot()
    ns = "{http://www.w3.org/2000/svg}"
    assert "15 kN" in [t.text for t in root.iter(f"{ns}text")]
    assert root.find(f"{ns}defs/{ns}pattern") is not None  # The hatched occupancy load.
    mpl_svg = bz.draw(diagram, tmp_path / "m.svg", renderer=bz.MatplotlibRenderer())
    assert "<text" in mpl_svg.read_text()


def test_png_size_follows_settings(tmp_path, diagram):
    import matplotlib.image as mpimg

    path = bz.MatplotlibRenderer(width=4, dpi=100).save(diagram, tmp_path / "s.png")
    assert mpimg.imread(path).shape[1] == 400


def test_svg_embed_font(diagram):
    assert "@font-face" in bz.SVGRenderer(embed_font=True).to_string(diagram)


FEATURES = pathlib.Path(__file__).parents[1] / "examples" / "drawing_features.yaml"


@pytest.fixture(scope="module")
def features():
    return bz.load_scheme(FEATURES)


def test_springs_parse_in_every_form(features):
    b2 = features["B2"]
    assert b2.node_supports == ["rotational_spring", "roller", "spring", "free"]
    spec = from_scheme(b2)
    assert spec.support_labels == ["8000 kN·m/rad", None, "12 kN/mm", None]
    b = bz.Beam.model_validate({"spans": [4, 4], "supports": ["pinned", {"type": "v_spring", "k": 5}, "m_spring"]})
    assert b.node_supports == ["pin", "spring", "rotational_spring"]


@pytest.mark.parametrize("supports, message", [
    (["pin", {"type": "roller", "k": 5}, "roller"], "only springs"),
    (["pin", "roller", "bracket"], "bracket"),
])
def test_bad_supports(supports, message):
    with pytest.raises(Exception, match=message):
        bz.Beam.model_validate({"spans": [4, 4], "supports": supports})


def test_spring_stiffness_dimension_checked():
    with pytest.raises(Exception, match="spring"):
        bz.parse_scheme({"_environment": "structural",
                         "B": {"spans": ["4 m"], "supports": ["pin", {"spring": "5 kN"}]}})


def test_spring_glyphs():
    from beamz9000.graphics import glyphs as g
    body, strokes = g.support("spring", 1.0)
    assert body.is_empty and strokes.bounds[3] == pytest.approx(0.0)
    body, strokes = g.support("rotational_spring", 1.0)
    assert not body.is_empty and len(strokes.geoms) == 6  # ground, 4 ticks, spiral


def test_depth_draws_rectangle_with_loads_on_top(features):
    d = bz.beam_diagram(features, beam_id="B2")
    loads, beam, supports = d.children[:3]
    assert beam.geometry.geom_type == "Polygon"
    assert beam.bounds[1] == pytest.approx(-0.225) and beam.bounds[3] == pytest.approx(0.225)
    assert loads.bounds[1] > 0.225
    roller = supports.children[1]
    assert max(c.bounds[3] for c in roller.children) == pytest.approx(-0.225)


def test_fixed_wall_covers_depth_without_growing(features):
    d = bz.beam_diagram(features, beam_id="B3")
    wall_body = d.children[2].children[0].children[0]
    x0, y0, x1, y1 = wall_body.bounds
    assert x1 == pytest.approx(0.0, abs=1e-9)
    assert y0 < -0.3 and y1 > 0.3  # Covers the 600 mm depth,
    assert x1 - x0 == pytest.approx(bz.Layout().glyph_width / 2 * 4.0)  # but keeps the glyph's thickness.


def test_angled_point_load(features):
    spec = from_scheme(features["B2"])
    load = spec.loads[0]
    assert load.angle == 30
    item = [i for i in bz.beam_diagram(spec).children[0].children[0].children if i.key == "D"][0]
    shaft = item.children[0].geometry
    (x_tail, y_tail), (x_end, _) = shaft.coords
    assert x_tail < load.x1 and y_tail > 0  # Tail tilted counter-clockwise, up and to the left.


def test_angle_limits():
    with pytest.raises(Exception, match="angle"):
        bz.Beam.model_validate({"spans": [4], "loads": [{"point": {"p": 1, "loc": 1, "angle": 120}}]})


def test_labels_are_unsigned_and_zero_labels_dropped(features):
    texts = [t.text for t in flatten(bz.beam_diagram(features, beam_id="B2")) if isinstance(t, Text)]
    assert "8 kN" in texts and "-8 kN" not in texts
    spec = from_scheme(features["B3"])
    tri = [l for l in spec.loads if l.kind == "line"][0]
    assert (tri.label1, tri.label2) == ("", "8 kN/m")


def test_node_labels(features):
    d = bz.beam_diagram(features, beam_id="B2")
    labels = d.children[3].children
    assert [t.text for t in labels] == ["A", "B", "C", "D"]
    assert len({t.anchor[1] for t in labels}) == 1  # One shared line,
    assert labels[0].anchor[1] < d.children[2].bounds[1]  # below the supports,
    assert d.children[4].bounds[3] < min(t.bounds[1] for t in labels)  # above the dimensions.
    assert bz.Beam.model_validate({"spans": [1] * 27, "node_labels": "auto"}).labels[26:] == ["AA", "AB"]
    with pytest.raises(Exception, match="node_labels"):
        bz.Beam.model_validate({"spans": [4], "labels": ["A"]})


def test_line_weights_thin_with_a_narrow_output():
    from beamz9000.render.frame import REFERENCE_WIDTH_PT, line_factor, line_weight

    assert line_factor(REFERENCE_WIDTH_PT * 2) == 1.0  # Never thickened.
    assert line_factor(REFERENCE_WIDTH_PT / 2) == pytest.approx(0.5)
    assert line_factor(100, line_scale=1.0) == 1.0
    assert line_weight(4.0, 0.5) == 2.0
    assert line_weight(0.5, 0.1) == 0.25  # Floor.
    d = bz.beam_diagram("examples/gallery.yaml", beam_id="simple_udl")
    wide, narrow = (bz.SVGRenderer(width=w).to_string(d) for w in (1152, 384))
    # In drawing units the beam stroke is the same fraction of the drawing.
    import re

    def beam_stroke(svg):
        return max(float(v) for v in re.findall(r'stroke-width="([\d.]+)"', svg))

    assert beam_stroke(narrow) == pytest.approx(beam_stroke(wide), rel=1e-3)


def test_pressure_loads_show_trib_widths_and_legend_pressures():
    scheme = bz.parse_scheme({"_environment": "structural", "B": {
        "spans": ["6 m"],
        "loads": [{"pressure": {"q": "1.2 kPa", "trib": "2.5 m", "case": "SDL"}},
                  {"pressure": {"q": "0.8 kPa", "trib_width1": "1 m", "trib_width2": "2 m", "case": "SDL"}}],
    }})
    spec = bz.as_spec(scheme)
    assert [(l.label1, l.label2) for l in spec.loads] == [("2.5 m", None), ("1 m", "2 m")]
    assert [k.text for k in spec.keys] == ["SDL (1.2 kPa, 0.8 kPa)"]
