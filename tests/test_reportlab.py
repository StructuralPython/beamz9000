"""The ReportLab renderer and the ymprint block."""

import pathlib

import pytest

import beamz9000 as bz

pytest.importorskip("reportlab")
from beamz9000.graphics.elements import Text, flatten  # noqa: E402
from beamz9000.render.reportlab import ReportLabRenderer  # noqa: E402

pymupdf = pytest.importorskip("pymupdf")

EXAMPLES = pathlib.Path(__file__).parents[1] / "examples"


def _pdf_text(data: bytes):
    doc = pymupdf.open(stream=data, filetype="pdf")
    page = doc[0]
    spans = [s for b in page.get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"]]
    return page.rect, page.get_text(), spans


def test_pdf_has_exact_size_and_searchable_text():
    r = ReportLabRenderer(width=468, height=200)
    diagram = bz.beam_diagram(EXAMPLES / "beam_scheme.yaml", bz.Layout(font_size_pt=8),
                              aspect=r.aspect, margin=r.margin, width=r.width_pt)
    rect, text, spans = _pdf_text(r.to_bytes(diagram))
    assert (rect.width, rect.height) == pytest.approx((468, 200))
    for label in ["15 kN", "5 kN·m", "3.4 kPa", "4500 mm", "residential"]:
        assert label in text
    assert {round(s["size"]) for s in spans} == {8}


def test_natural_height_follows_drawing():
    diagram = bz.beam_diagram(EXAMPLES / "beam_scheme.yaml")
    r = ReportLabRenderer(width=300)
    w, h = r.size(diagram)
    x0, y0, x1, y1 = bz.render.frame(diagram.bounds, r.margin)
    assert (w, h) == pytest.approx((300, 300 * (y1 - y0) / (x1 - x0)))


def test_text_is_placed_where_it_was_measured():
    diagram = bz.beam_diagram(EXAMPLES / "gallery.yaml", beam_id="simple_udl")
    r = ReportLabRenderer(width=400)
    _, _, spans = _pdf_text(r.to_bytes(diagram))
    x0, y0, x1, y1 = bz.render.frame(diagram.bounds, r.margin)
    k = 400 / (x1 - x0)
    height = r.size(diagram)[1]
    texts = {t.text: t for t in flatten(diagram) if isinstance(t, Text)}
    for span in spans:
        t = texts[span["text"]]
        bx0, _, bx1, _ = t.bounds
        # PDF x runs from the left; the measured box and the drawn span agree.
        assert span["bbox"][0] == pytest.approx((bx0 - x0) * k, abs=0.5)
        assert span["bbox"][2] == pytest.approx((bx1 - x0) * k, abs=1.0)
        assert 0 <= span["bbox"][1] <= height


def test_flowable_and_suffix_check(tmp_path):
    diagram = bz.beam_diagram(EXAMPLES / "gallery.yaml", beam_id="overhang")
    r = ReportLabRenderer(width=250, height=120)
    f = r.flowable(diagram)
    assert f.wrap(500, 500) == (250, 120)
    with pytest.raises(ValueError, match="PDF"):
        r.save(diagram, tmp_path / "x.png")


# --- ymprint block --------------------------------------------------------------------

ymprint = pytest.importorskip("ymprint")


def _render(tmp_path, doc: dict) -> bytes:
    from beamz9000.ymprint import app

    for f in EXAMPLES.glob("*.yaml"):
        (tmp_path / f.name).write_text(f.read_text())
    out = tmp_path / "out.pdf"
    app.render(doc, out, base_dir=tmp_path, discover_config=False)
    return out.read_bytes()


def _all_text(data: bytes) -> str:
    return "".join(p.get_text() for p in pymupdf.open(stream=data, filetype="pdf"))


def test_block_from_scheme_file(tmp_path):
    data = _render(tmp_path, {"Beams": [
        {"_beam_b1": {"scheme": "beam_scheme.yaml", "caption": "Beam B1 loading"}},
        {"_beam_f": {"scheme": "gallery.yaml", "beam": "floor_beam", "height": "50 mm"}},
    ]})
    text = _all_text(data)
    for label in ["15 kN", "Beam B1 loading", "4.4 kPa", "12.6 m"]:
        assert label in text


def test_block_inline_beam(tmp_path):
    data = _render(tmp_path, {"Beams": [{"_beam_c1": {
        "beam": {"spans": ["3 m"], "cantilever": "right",
                 "loads": [{"point": {"p": "10 kN", "loc": "L", "case": "L"}}]},
        "width_ratio": 0.5, "legend": "none",
    }}]})
    text = _all_text(data)
    assert "10 kN" in text and "3 m" in text
    assert "Load cases" not in text


def test_block_takes_a_beam_object(tmp_path):
    from beamz9000.ymprint import beam_block

    beam = bz.load_scheme(EXAMPLES / "gallery.yaml")["overhang"]
    context = {"frames": {"all_pages": {"width": 400, "height": 600}}, "base_dir": str(tmp_path)}
    (table,) = beam_block("_beam", {"beam": beam, "height": 150}, context)
    flowable = table._cellvalues[0][0]
    assert flowable.wrap(400, 600) == pytest.approx((400, 150))


def test_tall_diagram_is_limited_to_the_page(tmp_path):
    from beamz9000.ymprint import beam_block

    beam = bz.load_scheme(EXAMPLES / "beam_scheme.yaml")["B1"]
    context = {"frames": {"all_pages": {"width": 400, "height": 300}}, "base_dir": str(tmp_path)}
    (table,) = beam_block("_beam", {"beam": beam}, context)
    assert table._cellvalues[0][0].height == pytest.approx(300 * 0.6)


@pytest.mark.parametrize("value, message", [
    ({}, "give a `scheme` file"),
    ({"scheme": "missing.yaml"}, "not found"),
    ({"beam": {"spans": ["3 m"], "loads": [{"point": {"p": "1 kN", "loc": "9 m"}}]}}, "off the beam"),
    ({"beam": {"spans": ["3 m"]}, "height": "tall"}, "not a length"),
    ({"beam": {"spans": ["3 m"]}, "colour": "red"}, "colour"),
])
def test_block_errors_name_the_block(tmp_path, value, message):
    from ymprint.errors import BlockError

    from beamz9000.ymprint import beam_block

    context = {"frames": {"all_pages": {"width": 400, "height": 600}}, "base_dir": str(tmp_path)}
    with pytest.raises(BlockError, match=message) as err:
        beam_block("_beam_x", value, context)
    assert "_beam_x" in str(err.value)


def test_to_points():
    from beamz9000.ymprint import to_points

    assert to_points(72) == 72
    assert to_points("1 in") == 72
    assert to_points("25.4 mm") == pytest.approx(72)
    assert to_points("180") == 180


def test_block_is_published_as_an_entry_point():
    from importlib.metadata import entry_points

    from beamz9000.ymprint import beam_block

    (ep,) = [ep for ep in entry_points(group="ymprint.blocks") if ep.dist and ep.dist.name == "beamz9000"]
    assert ep.name == "_beam"
    assert ep.load() is beam_block
