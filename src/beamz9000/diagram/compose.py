"""
Composes a beam free-body diagram from glyphs, in strata from top to bottom:
load bands, the beam, supports, dimensions, with a legend to the right.

Every function here is pure: it takes a BeamSpec and a Layout (and, where it
stacks on earlier parts, the bounds of what is already placed) and returns
elements. `beam_diagram()` composes them in order.

A beam with a `depth` is drawn as a rectangle centred on y = 0: loads rest on
its top and supports hang from its bottom (fixed ends become walls at its
ends). Node labels sit under each node, between the supports and the
dimensions.

Loads are drawn in bands, one per legend key (load case, occupancy, or
"Factored"), stacked upward from the beam in the order keys first appear.
Within a band, loads are packed into rows so that no two items (glyph plus
label) overlap. Load heights are scaled per load type across the whole beam,
so bands can be compared by eye.
"""

from __future__ import annotations

import math
import pathlib
from dataclasses import dataclass
from typing import Optional, Union

from beamz9000.diagram.layout import Layout
from beamz9000.graphics import glyphs
from beamz9000.graphics.elements import Group, Shape, Text, group, translate
from beamz9000.spec import BeamSpec, SpecLoad, from_scheme

Bounds = tuple[float, float, float, float]

# Drawing order of the strata.
Z_LOAD_FILL, Z_LOAD, Z_BEAM, Z_SUPPORT, Z_DIMENSION, Z_TEXT = 1, 2, 3, 4, 2, 5


@dataclass(frozen=True)
class _Scale:
    """Turns load magnitudes into drawing heights."""

    length: float
    point_max: float
    line_max: float
    layout: Layout

    def size(self, frac: float) -> float:
        return frac * self.length

    def point(self, mag: float) -> float:
        return self._scaled(abs(mag), self.point_max, self.layout.point_height)

    def line(self, mag: float) -> float:
        return self._scaled(abs(mag), self.line_max, self.layout.line_height)

    def _scaled(self, mag, biggest, height):
        if biggest == 0 or mag == 0:
            return 0.0
        return max(mag / biggest, self.layout.min_fraction) * height * self.length


def _scale_for(spec: BeamSpec, layout: Layout) -> _Scale:
    points = [abs(l.mag1) for l in spec.loads if l.kind == "point"]
    lines = [max(abs(l.mag1), abs(l.mag2 or 0)) for l in spec.loads if l.kind == "line"]
    return _Scale(spec.length, max(points, default=0.0), max(lines, default=0.0), layout)


def _font_size(layout: Layout, length: float) -> float:
    return layout.font_size * length


def label(text: str, anchor, layout: Layout, length: float, *, ha="center", va="bottom",
          color: Optional[str] = None, **fields) -> Text:
    """A diagram label in the layout's font."""
    return Text(
        text=text, anchor=tuple(anchor), ha=ha, va=va,
        font_family=layout.font_family, font_size=_font_size(layout, length),
        fill_color=color or layout.ink, z=Z_TEXT, **fields,
    )


# --- Beam and supports ---------------------------------------------------------


def _half_depth(spec: BeamSpec) -> float:
    return (spec.depth or 0.0) / 2


def beam_line(spec: BeamSpec, layout: Layout) -> Shape:
    """
    The beam: one heavy line on y = 0, or, with a depth, a rectangle centred
    on y = 0.
    """
    import shapely

    x0, x1 = spec.nodes[0], spec.nodes[-1]
    if spec.depth:
        d = _half_depth(spec)
        return Shape(
            geometry=shapely.box(x0, -d, x1, d), fill_color=layout.beam_fill,
            stroke_color=layout.ink, stroke_width=layout.beam_outline_width, z=Z_BEAM, role="beam",
        )
    return Shape(
        geometry=shapely.LineString([(x0, 0.0), (x1, 0.0)]),
        stroke_color=layout.ink, stroke_width=layout.beam_stroke_width, z=Z_BEAM, role="beam",
    )


def _facing(spec: BeamSpec, idx: int, kind: str) -> str:
    if kind != "fixed":
        return "up"
    if idx == 0:
        return "right"
    if idx == len(spec.nodes) - 1:
        return "left"
    return "up"


def supports(spec: BeamSpec, layout: Layout) -> Group:
    """
    A support glyph at each supported node, hanging from the beam's underside;
    free ends get nothing. A fixed end becomes a wall at the beam's end, sized
    to cover the beam's depth. A spring with a stiffness is labelled beside it.
    """
    L = spec.length
    gw = layout.glyph_width * L
    d = _half_depth(spec)
    labels = spec.support_labels or [None] * len(spec.nodes)
    parts = []
    for idx, (x, kind, k_label) in enumerate(zip(spec.nodes, spec.supports, labels)):
        if kind == "free":
            continue
        facing = _facing(spec, idx, kind)
        if facing == "up":
            anchor, width = (x, -d), None
        else:  # A wall at the beam's end, stretched to cover its depth.
            anchor, width = (x, 0.0), max(gw, 2 * d * 1.2 + gw / 2)
        size = gw
        body, strokes = glyphs.support(kind, size, width=width)
        items = [
            Shape(geometry=glyphs.place(body, anchor, facing), fill_color=layout.support_fill,
                  stroke_color=layout.ink, stroke_width=layout.stroke_width, z=Z_SUPPORT),
            Shape(geometry=glyphs.place(strokes, anchor, facing), stroke_color=layout.ink,
                  stroke_width=layout.stroke_width, z=Z_SUPPORT),
        ]
        if k_label:
            fs = _font_size(layout, L)
            x_right = max(it.bounds[2] for it in items if not it.is_empty)
            items.append(label(k_label, (x_right + layout.label_gap * fs, anchor[1] - glyphs.support_height(size) / 2),
                               layout, L, ha="left", va="center"))
        parts.append(group(items, role="support"))
    return group(parts, role="supports")


def node_labels(spec: BeamSpec, layout: Layout, supports_group: Group) -> Group:
    """Each node's label, centred under its node on a line below the lowest support."""
    L = spec.length
    fs = _font_size(layout, L)
    gap = layout.label_gap * fs
    by_node: dict[int, float] = {}
    supported = [i for i, k in enumerate(spec.supports) if k != "free"]
    for i, sup in zip(supported, supports_group.children):
        shapes = [c for c in sup.children if isinstance(c, Shape) and not c.is_empty]
        by_node[i] = min(c.bounds[1] for c in shapes)
    # All labels share one line, under the lowest support.
    bottom = min([*by_node.values(), -_half_depth(spec)])
    parts = [
        label(text, (x, bottom - gap), layout, L, va="top", font_weight="bold")
        for x, text in zip(spec.nodes, spec.node_labels or [])
        if text
    ]
    return group(parts, role="node_labels")


# --- Load items -----------------------------------------------------------------


def load_item(load: SpecLoad, scale: _Scale, color: str, layout: Layout) -> Group:
    """
    One load drawn with its base on y = 0, with its label(s) above it.
    Downward loads point at the base; upward loads point away from it.
    """
    L = scale.length
    gap = layout.label_gap * _font_size(layout, L)
    stroke = dict(stroke_color=color, stroke_width=layout.load_stroke_width, z=Z_LOAD)
    head = dict(fill_color=color, stroke_color=None, z=Z_LOAD)
    hl, hw = scale.size(layout.head_length), scale.size(layout.head_width)
    parts: list = []

    if load.kind == "point":
        h = scale.point(load.mag1)
        # The end away from the base, tilted counter-clockwise by 'angle' about the base.
        a = math.radians(load.angle)
        far = (load.x1 - h * math.sin(a), h * math.cos(a))
        base = (load.x1, 0.0)
        tail, tip = (far, base) if load.mag1 >= 0 else (base, far)
        shaft, arrowhead = glyphs.arrow(tail, tip, hl, hw)
        parts += [Shape(geometry=shaft, **stroke), Shape(geometry=arrowhead, **head),
                  label(load.label1, (far[0], far[1] + gap), layout, L, color=color)]

    elif load.kind == "moment":
        r = scale.size(layout.moment_radius)
        arc, arrowhead = glyphs.moment_arc(r, load.mag1 >= 0, hl, hw)
        lift = (0.0, r)
        parts += [Shape(geometry=glyphs.place(arc, lift), **stroke),
                  Shape(geometry=glyphs.place(arrowhead, lift), **head),
                  label(load.label1, (load.x1, 2 * r + gap), layout, L, color=color)]
        parts = [translate(p, load.x1, 0.0) if not isinstance(p, Text) else p for p in parts]

    else:
        h1, h2 = scale.line(load.mag1), scale.line(load.mag2)
        region = glyphs.trapezoid(load.x1, load.x2, h1, h2)
        shafts, heads = glyphs.line_load_arrows(
            load.x1, load.x2, h1, h2, scale.size(layout.arrow_spacing), hl, hw,
            upward=load.mag1 < 0 and (load.mag2 or 0) <= 0,
        )
        parts += [
            Shape(geometry=region, fill_color=color, fill_opacity=layout.load_fill_opacity,
                  hatch=layout.area_load_hatch if load.area_load else None,
                  stroke_color=color, stroke_width=layout.load_stroke_width, z=Z_LOAD_FILL),
            Shape(geometry=shafts, stroke_color=color, stroke_width=layout.load_stroke_width * 0.8, z=Z_LOAD),
            Shape(geometry=heads, **head),
        ]
        if load.label2 is None:
            parts.append(label(load.label1, ((load.x1 + load.x2) / 2, max(h1, h2) + gap), layout, L, color=color))
        else:
            parts += [label(load.label1, (load.x1, h1 + gap), layout, L, ha="left", color=color),
                      label(load.label2, (load.x2, h2 + gap), layout, L, ha="right", color=color)]

    return group(parts, key=load.key, role="load")


def pack_rows(extents: list[tuple[float, float]], gap: float) -> list[int]:
    """
    Returns a row index for each (x_min, x_max) extent: each goes, in order,
    into the lowest row where it overlaps nothing (with 'gap' clearance).
    """
    rows: list[list[tuple[float, float]]] = []
    placed = []
    for x0, x1 in extents:
        for idx, row in enumerate(rows):
            if all(x1 + gap <= a or x0 >= b + gap for a, b in row):
                row.append((x0, x1))
                placed.append(idx)
                break
        else:
            rows.append([(x0, x1)])
            placed.append(len(rows) - 1)
    return placed


def load_bands(spec: BeamSpec, layout: Layout, base: float = 0.0) -> Group:
    """
    The loads, in one band per legend key stacked upward from 'base'. Each
    band packs its loads into as many rows as needed to avoid overlaps.
    """
    scale = _scale_for(spec, layout)
    L = spec.length
    colors = {k.name: layout.color(i) for i, k in enumerate(spec.keys)}
    y = base + scale.size(layout.beam_clearance)
    bands = []
    for key in spec.keys:
        items = [load_item(l, scale, colors[key.name], layout) for l in spec.loads if l.key == key.name]
        if not items:
            continue
        rows = pack_rows([(i.bounds[0], i.bounds[2]) for i in items], scale.size(layout.item_gap))
        placed = []
        row_base = y
        for row in range(max(rows) + 1):
            members = [i for i, r in zip(items, rows) if r == row]
            placed += [translate(i, 0.0, row_base) for i in members]
            row_base += max(i.bounds[3] for i in members) + scale.size(layout.row_gap)
        bands.append(group(placed, key=key.name, role="band"))
        y = row_base - scale.size(layout.row_gap) + scale.size(layout.band_gap)
    return group(bands, role="loads")


# --- Dimensions and legend ----------------------------------------------------------


def dimensions(spec: BeamSpec, layout: Layout, top: float) -> Group:
    """Span dimensions below 'top', then the overall dimension below those."""
    L = spec.length
    fs = _font_size(layout, L)
    gap = layout.label_gap * fs
    tick = layout.tick_size * L
    style = dict(stroke_color=layout.ink, stroke_width=layout.dimension_stroke_width, z=Z_DIMENSION)
    y = top - layout.dimension_gap * L - fs
    parts = [Shape(geometry=glyphs.dimension_line(spec.nodes, y, tick), **style)]
    for (a, b), text in zip(zip(spec.nodes, spec.nodes[1:]), spec.span_labels):
        parts.append(label(text, ((a + b) / 2, y + gap), layout, L))
    if len(spec.spans) > 1:
        y -= layout.dimension_spacing * L
        parts.append(Shape(geometry=glyphs.dimension_line([spec.nodes[0], spec.nodes[-1]], y, tick), **style))
        parts.append(label(spec.length_label, ((spec.nodes[0] + spec.nodes[-1]) / 2, y + gap), layout, L))
    return group(parts, role="dimensions")


def legend(spec: BeamSpec, layout: Layout, drawing: Bounds) -> Group:
    """The legend keys, right of the drawing and aligned to its top."""
    if not spec.keys:
        return group(role="legend")
    L = spec.length
    fs = _font_size(layout, L)
    x = drawing[2] + layout.legend_gap * L
    title = layout.legend_title or (
        "Load cases & occupancies" if any(k.kind == "occupancy" for k in spec.keys) else "Load cases"
    )
    parts = [label(title, (x, drawing[3]), layout, L, ha="left", va="top")]
    pitch = layout.legend_row * fs
    s = layout.swatch_size * L
    y = drawing[3] - pitch * 1.5
    for i, key in enumerate(spec.keys):
        color = layout.color(i)
        parts += [
            Shape(geometry=glyphs.swatch(x, y - s / 2, s), fill_color=color, fill_opacity=0.6,
                  stroke_color=color, stroke_width=layout.stroke_width, z=Z_TEXT, key=key.name),
            label(key.name, (x + s + 0.6 * fs, y), layout, L, ha="left", va="center", key=key.name),
        ]
        y -= pitch
    return group(parts, role="legend")


# --- Whole diagram -------------------------------------------------------------------


Drawable = Union[BeamSpec, "Beam", str, pathlib.Path]  # noqa: F821


def as_spec(obj, beam_id: Optional[str] = None) -> BeamSpec:
    """
    Returns a BeamSpec from a BeamSpec, a scheme Beam, a Scheme, or a path to
    a scheme file. A scheme with several beams needs 'beam_id'.
    """
    from beamz9000.scheme import Beam, Scheme, load_scheme

    if isinstance(obj, BeamSpec):
        return obj
    if isinstance(obj, Beam):
        return from_scheme(obj, name=beam_id)
    if isinstance(obj, (str, pathlib.Path)):
        obj = load_scheme(obj)
    if isinstance(obj, Scheme):
        if beam_id is None:
            if len(obj.beams) != 1:
                raise ValueError(f"the scheme has {len(obj.beams)} beams; name one with beam_id")
            beam_id = next(iter(obj.beams))
        return from_scheme(obj[beam_id], name=beam_id)
    raise TypeError(f"cannot draw a {type(obj).__name__}")


def beam_diagram(obj, layout: Optional[Layout] = None, beam_id: Optional[str] = None) -> Group:
    """
    Returns the free-body diagram of a beam as one Group: load bands above the
    beam, supports and node labels, dimensions below, and the legend to the right. 'obj' is
    anything `as_spec` accepts.
    """
    spec = as_spec(obj, beam_id)
    layout = layout or Layout()
    beam = beam_line(spec, layout)
    sup = supports(spec, layout)
    labels = node_labels(spec, layout, sup)
    loads = load_bands(spec, layout, base=_half_depth(spec))
    below = [g.bounds[1] for g in (sup, labels) if len(g)]
    lowest = min([*below, -_half_depth(spec)])
    dims = dimensions(spec, layout, top=lowest)
    body = group(loads, beam, sup, labels, dims)
    parts = [loads, beam, sup, labels, dims]
    if layout.legend:
        parts.append(legend(spec, layout, body.bounds))
    return group(parts, role="diagram")
