import math

import pytest
import shapely

from beamz9000.graphics import glyphs as g
from beamz9000.graphics import text as tx
from beamz9000.graphics.elements import (
    Group, Shape, Text, flatten, group, mirror_x, restyle, rotate, scale, translate,
)


def test_support_proportions_match_fbd_plotting():
    body, ground = g.support("pin", 1.0)
    assert body.bounds == pytest.approx((-0.25, -0.5, 0.25, 0.0))
    assert len(ground.geoms) == 5  # ground line + 4 ticks
    assert ground.bounds == pytest.approx((-0.7, -0.7, 0.5, -0.5))
    roller, _ = g.support("roller", 1.0)
    assert roller.bounds == pytest.approx((-0.25, -0.5, 0.25, 0.0), abs=1e-9)
    assert g.support("free", 1.0)[0].is_empty


def test_orient_puts_wall_on_the_correct_side():
    body, _ = g.support("fixed", 1.0)
    assert g.orient(body, "right").bounds == pytest.approx((-0.5, -0.25, 0.0, 0.25))
    assert g.orient(body, "left").bounds == pytest.approx((0.0, -0.25, 0.5, 0.25))
    assert g.place(body, (3, 1)).bounds == pytest.approx((2.75, 0.5, 3.25, 1.0))


def test_arrow_and_short_arrow():
    shaft, head = g.arrow((0, 1), (0, 0), 0.2, 0.14)
    assert list(shaft.coords) == [(0, 1), (0, pytest.approx(0.2))]
    assert head.bounds == pytest.approx((-0.07, 0, 0.07, 0.2))
    shaft, head = g.arrow((0, 0.1), (0, 0), 0.2, 0.14)
    assert shaft.is_empty and head.bounds[3] == pytest.approx(0.1)


def test_moment_arc_direction():
    arc, head = g.moment_arc(1.0, True, 0.3, 0.2)
    assert arc.coords[0] == pytest.approx((math.cos(math.radians(-45)), math.sin(math.radians(-45))))
    # Counter-clockwise: the head ends at the lower left.
    assert head.centroid.x < 0 and head.centroid.y < 0
    _, head_cw = g.moment_arc(1.0, False, 0.3, 0.2)
    assert head_cw.centroid.x > 0


def test_line_load_arrows():
    shafts, heads = g.line_load_arrows(0, 3, 0.5, 1.0, 0.5, 0.14, 0.1)
    assert len(heads.geoms) == 7
    assert all(h.bounds[1] == pytest.approx(0) for h in heads.geoms)
    _, up = g.line_load_arrows(0, 3, 0.5, 1.0, 0.5, 0.14, 0.1, upward=True)
    assert up.geoms[0].bounds[3] == pytest.approx(0.5)


def test_hatch_lines_clip_to_region():
    region = g.trapezoid(0, 3, 1, 0.5)
    lines = g.hatch_lines(region, 0.2)
    assert len(lines.geoms) > 5
    assert region.buffer(1e-9).contains(lines)


def test_text_measure_is_shaped():
    # libraqm applies kerning: "AV" is narrower than "A" + "V".
    assert tx.measure("AV").advance < tx.measure("A").advance + tx.measure("V").advance
    assert tx.measure("Factored").advance == pytest.approx(4.289, abs=1e-3)
    assert tx.measure("x", font_size=2.0).advance == pytest.approx(2 * tx.measure("x").advance)


@pytest.mark.parametrize("ha, va", [("left", "baseline"), ("center", "center"), ("right", "top"), ("center", "bottom")])
def test_text_alignment(ha, va):
    t = Text(text="15 kN", anchor=(10, 5), font_size=2, ha=ha, va=va)
    x0, y0, x1, y1 = t.bounds
    e = tx.measure_text(t)
    assert x1 - x0 == pytest.approx(e.advance)
    assert {"left": x0, "center": (x0 + x1) / 2, "right": x1}[ha] == pytest.approx(10)
    baseline = {"baseline": 5, "bottom": 5 + e.descent, "top": 5 - e.ascent, "center": 5 - e.cap_height / 2}[va]
    assert y0 == pytest.approx(baseline - e.descent)



def test_transforms_are_functional_and_walk_groups():
    s = Shape(geometry=shapely.box(0, 0, 1, 1), fill_color="red")
    t = Text(text="A", anchor=(0.5, 2), ha="left")
    grp = group(s, t)
    moved = rotate(translate(grp, 1, 0), 90)
    assert grp.children[0].bounds == (0, 0, 1, 1)  # Original untouched.
    assert moved.children[0].bounds == pytest.approx((-1, 1, 0, 2))
    assert moved.children[1].anchor == pytest.approx((-2, 1.5))
    assert moved.children[1].rotation == 0
    assert rotate(t, 90, turn_text=True).rotation == 90
    assert scale(t, 2).font_size == 2
    assert mirror_x(t, 0).ha == "right"


def test_restyle_validates():
    s = Shape(geometry=shapely.box(0, 0, 1, 1))
    assert restyle(group(s), stroke_color="blue", z=3).children[0].z == 3
    with pytest.raises(ValueError):
        restyle(s, colour="blue")
    with pytest.raises(ValueError):
        restyle(s, fill_opacity=2)


def test_flatten_orders_by_z_and_drops_empty():
    a = Shape(geometry=shapely.box(0, 0, 1, 1), z=2)
    b = Shape(geometry=shapely.box(0, 0, 1, 1), z=1)
    e = Shape(geometry=shapely.LineString())
    assert flatten(group(a, group(b, e))) == [b, a]


def test_json_round_trip_is_exact():
    grp = group(
        Shape(geometry=g.roller_body(0.37), hatch="//", line_type="dashed"),
        Text(text="5 kN·m", anchor=(1 / 3, 2 / 7)),
        group(Shape(geometry=g.ground(1.0)), key="D"),
    )
    assert Group.model_validate_json(grp.model_dump_json()) == grp
