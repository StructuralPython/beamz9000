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
    return from_scheme(bz.load_scheme(EXAMPLE)["B1"], "B1")


@pytest.fixture(scope="module")
def diagram(spec):
    return bz.beam_diagram(spec)


def test_spec_matches_scheme(spec):
    assert spec.nodes == [0.0, 4.5, 7.0]
    assert [k.name for k in spec.keys] == ["L", "Factored", "D", "residential"]
    occ = [l for l in spec.loads if l.key == "residential"][0]
    assert (occ.mag1, occ.mag2, occ.label1, occ.area_load) == (10200.0, 5100.0, "3.4 kPa", True)
    varying = [l for l in spec.loads if l.label2][0]
    assert (varying.label1, varying.label2) == ("1 kN/m", "4 kN/m")


def test_split_occupancies():
    spec = from_scheme(bz.load_scheme(EXAMPLE)["B1"], split_occupancies=True)
    assert "residential" not in [k.name for k in spec.keys]
    assert len([l for l in spec.loads if l.area_load]) == 2


def test_pack_rows():
    assert pack_rows([(0, 1), (0.5, 1.5), (2, 3), (1.2, 1.4), (0.9, 2.1)], gap=0.1) == [0, 1, 0, 0, 2]
    assert pack_rows([(0, 1), (1.05, 2)], gap=0.1) == [0, 1]


def test_strata_order(diagram):
    loads, beam, supports, dims, legend = diagram.children
    assert [c.role for c in diagram.children] == ["loads", "beam", "supports", "dimensions", "legend"]
    assert loads.bounds[1] > 0  # Loads sit above the beam,
    assert supports.bounds[3] <= 1e-9  # supports below it,
    assert dims.bounds[3] < supports.bounds[1]  # dimensions below the supports,
    assert legend.bounds[0] > max(loads.bounds[2], dims.bounds[2])  # legend to the right.


def test_bands_stack_in_key_order_without_overlap(spec, diagram):
    bands = diagram.children[0].children
    assert [b.key for b in bands] == ["L", "Factored", "D", "residential"]
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
    for expected in ["15 kN", "10 kN", "2.5 kN/m", "1 kN/m", "4 kN/m", "3.4 kPa", "5 kN·m",
                     "4500 mm", "2500 mm", "7000 mm", "Load cases & occupancies", "residential"]:
        assert expected in texts


def test_plain_number_scheme_draws():
    d = bz.beam_diagram(bz.load_scheme("B:\n  spans: [6, 4]\n  loads:\n    - dist: {w: 2}\n"))
    assert [t.text for t in flatten(d) if isinstance(t, Text)][-1] == "Factored"


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
