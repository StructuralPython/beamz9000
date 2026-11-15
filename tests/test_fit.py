"""Fitting diagrams to a target size: exact output size, stretch, legend placement."""

import pathlib
import xml.etree.ElementTree as ET

import matplotlib.image as mpimg
import pytest

import beamz9000 as bz
from beamz9000.diagram.compose import _shape, fitted_scale
from beamz9000.render import frame
from beamz9000.spec import from_scheme

EXAMPLES = pathlib.Path(__file__).parents[1] / "examples"


@pytest.fixture(scope="module")
def spec():
    return from_scheme(bz.load_scheme(EXAMPLES / "beam_scheme.yaml")["B1"], "B1", analyze=False)


def _part(diagram, role):
    return next(c for c in diagram.children if c.role == role)


def _legend_position(diagram) -> str:
    legend, loads = _part(diagram, "legend"), _part(diagram, "loads")
    return "top" if legend.bounds[1] >= loads.bounds[3] else "right"


def test_frame_pads_then_matches_aspect():
    assert frame((0, 0, 10, 2), 0.1) == pytest.approx((-1, -1, 11, 3))
    x0, y0, x1, y1 = frame((0, 0, 10, 2), 0.1, aspect=2)
    assert (x1 - x0) / (y1 - y0) == pytest.approx(2)
    assert ((x0 + x1) / 2, (y0 + y1) / 2) == pytest.approx((5, 1))  # Centred.
    x0, y0, x1, y1 = frame((0, 0, 10, 2), 0.1, aspect=6)
    assert (x1 - x0, y1 - y0) == pytest.approx((24, 4))  # Widened, not heightened.


def test_renderers_output_exact_size(tmp_path, spec):
    diagram = bz.beam_diagram(spec)
    png = bz.MatplotlibRenderer(width=4, height=3, dpi=100).save(diagram, tmp_path / "a.png")
    assert mpimg.imread(png).shape[:2] == (300, 400)
    svg = ET.fromstring(bz.SVGRenderer(width=800, height=200).to_string(diagram))
    assert (svg.get("width"), svg.get("height")) == ("800", "200")
    vb = [float(v) for v in svg.get("viewBox").split()]
    assert vb[2] / vb[3] == pytest.approx(4, rel=1e-5)
    assert bz.SVGRenderer(width=800).aspect is None
    assert bz.MatplotlibRenderer(width=6, height=2).aspect == 3


def test_wide_target_keeps_legend_right_and_squeezes(spec):
    natural = bz.beam_diagram(spec)
    wide = bz.beam_diagram(spec, aspect=4.0)
    assert _legend_position(wide) == "right"
    assert _part(wide, "loads").bounds[3] < _part(natural, "loads").bounds[3]


def test_tall_target_moves_legend_on_top(spec):
    diagram = bz.beam_diagram(spec, aspect=1.6)
    assert _legend_position(diagram) == "top"
    legend = _part(diagram, "legend")
    drawing = bz.Group(children=[c for c in diagram.children if c.role != "legend"]).bounds
    # The legend starts at the drawing's left edge and stays within its width.
    assert legend.bounds[0] == pytest.approx(drawing[0], abs=1e-6)
    assert legend.bounds[2] <= drawing[2] + 1e-6


def test_stretch_matches_target_when_in_range(spec):
    layout = bz.Layout(legend_position="right")
    natural = _shape(bz.beam_diagram(spec, layout).bounds, 0.02)
    for aspect in (natural * 0.85, natural * 1.15):  # Needs a stretch above and below 1.
        diagram = bz.beam_diagram(spec, layout, aspect=aspect)
        assert _shape(diagram.bounds, 0.02) == pytest.approx(aspect, rel=0.01)


def test_fit_is_never_smaller_than_the_natural_layout(spec):
    for aspect in (1.0, 1.8, 3.0, 5.0):
        natural = bz.beam_diagram(spec)
        fitted = bz.beam_diagram(spec, aspect=aspect)
        assert fitted_scale(fitted.bounds, aspect) >= fitted_scale(natural.bounds, aspect) * 0.999


def test_stretch_off_and_fixed_position(spec):
    layout = bz.Layout(stretch=(1, 1), legend_position="right")
    natural = bz.beam_diagram(spec, layout)
    fitted = bz.beam_diagram(spec, layout, aspect=1.2)
    assert fitted.bounds == pytest.approx(natural.bounds)
    assert _legend_position(fitted) == "right"


def test_legend_on_top_without_a_fit(spec):
    diagram = bz.beam_diagram(spec, bz.Layout(legend_position="top"))
    assert _legend_position(diagram) == "top"


def test_top_legend_wraps_to_the_drawing_width():
    scheme = bz.parse_scheme({"B": {
        "spans": [1000],
        "loads": [{"point": {"p": 1, "loc": 500, "case": f"Case {i}"}} for i in range(8)],
    }})
    diagram = bz.beam_diagram(scheme, bz.Layout(legend_position="top"))
    legend = _part(diagram, "legend")
    drawing_right = max(c.bounds[2] for c in diagram.children if c.role != "legend")
    assert legend.bounds[2] <= drawing_right + 1e-6
    rows = {round(c.bounds[1], 6) for c in legend.children}
    assert len(rows) > 1


@pytest.mark.parametrize("stretch", [(0, 1), (1.2, 2), (0.5, 0.9)])
def test_bad_stretch(stretch):
    with pytest.raises(ValueError, match="stretch"):
        bz.Layout(stretch=stretch)


def test_bad_aspect(spec):
    with pytest.raises(ValueError, match="aspect"):
        bz.beam_diagram(spec, aspect=0)


def test_draw_fits_to_the_renderer(tmp_path):
    path = bz.draw(EXAMPLES / "beam_scheme.yaml", tmp_path / "f.png",
                   renderer=bz.MatplotlibRenderer(width=4, height=4, dpi=50))
    assert mpimg.imread(path).shape[:2] == (200, 200)


@pytest.mark.parametrize("width", [300.0, 451.0, 900.0])
def test_overall_dimension_clears_span_labels(width):
    """Large text on a long beam: the overall dimension sits below the span row and its labels."""
    from beamz9000.graphics.elements import Shape, Text, flatten

    diagram = bz.beam_diagram(EXAMPLES / "gallery.yaml", bz.Layout(font_size_pt=8), "floor_beam",
                              aspect=width / 127.6, width=width)
    texts = [t for t in flatten(_part(diagram, "dimensions")) if isinstance(t, Text)]
    overall = next(t for t in texts if t.text == "12.6 m")
    spans = [t for t in texts if t is not overall]
    span_line = next(s for s in flatten(_part(diagram, "dimensions")) if isinstance(s, Shape))
    assert overall.bounds[3] < min(span_line.bounds[1], *(t.bounds[1] for t in spans))


def _scheme(text):
    import yaml
    return bz.parse_scheme(yaml.safe_load(text))


def _legend_role_bounds(diagram):
    parts = {c.role: c for c in diagram.children}
    return parts.get("legend"), parts["beam"]


def test_scheme_display_legend_top():
    scheme = _scheme(
        "B:\n  spans: [4]\n  loads: [{dist: {w: 2, case: D}}]\n  display: {legend: top}\n"
    )
    legend, beam = _legend_role_bounds(bz.beam_diagram(scheme))
    assert legend.bounds[1] > beam.bounds[3]  # Above the beam, not beside it.
    # A Layout that sets the placement wins over the scheme.
    legend, beam = _legend_role_bounds(bz.beam_diagram(scheme, bz.Layout(legend_position="right")))
    assert legend.bounds[0] > beam.bounds[2]


def test_scheme_display_legend_none():
    for value in ("none", "false"):
        scheme = _scheme(
            f"B:\n  spans: [4]\n  loads: [{{dist: {{w: 2, case: D}}}}]\n  display: {{legend: {value}}}\n"
        )
        legend, _ = _legend_role_bounds(bz.beam_diagram(scheme))
        assert legend is None or not len(legend)


def test_scheme_display_rejects_unknown_options():
    import pydantic
    with pytest.raises(pydantic.ValidationError):
        _scheme("B:\n  spans: [4]\n  display: {legend: left}\n")
