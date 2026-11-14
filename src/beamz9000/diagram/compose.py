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
from typing import Optional

from beamz9000.diagram.layout import Layout
from beamz9000.graphics import glyphs
from beamz9000.graphics.elements import Group, Shape, Text, group, translate
from beamz9000.render.frame import frame
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
    to cover the beam's depth. A spring with a stiffness is labelled beside it,
    or under it when there is no room beside it.
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
            items.append(_stiffness_label(spec, layout, idx, k_label, group(items).bounds))
        parts.append(group(items, role="support"))
    return group(parts, role="supports")


def _stiffness_label(spec: BeamSpec, layout: Layout, idx: int, text: str, glyph: Bounds) -> Text:
    """
    A spring's stiffness label: right of its glyph if that clears the next
    support, else left of it if that clears the previous one, else under it.
    """
    L = spec.length
    gap = layout.label_gap * _font_size(layout, L)
    half = layout.glyph_width * L / 2
    others = [x for i, (x, k) in enumerate(zip(spec.nodes, spec.supports)) if k != "free" and i != idx]
    right_limit = min((x - half - gap for x in others if x > spec.nodes[idx]), default=math.inf)
    left_limit = max((x + half + gap for x in others if x < spec.nodes[idx]), default=-math.inf)
    y = (glyph[1] + glyph[3]) / 2 if glyph[3] <= -_half_depth(spec) + 1e-9 else glyph[1] + (glyph[3] - glyph[1]) / 4
    right = label(text, (glyph[2] + gap, y), layout, L, ha="left", va="center")
    if right.bounds[2] <= right_limit:
        return right
    left = label(text, (glyph[0] - gap, y), layout, L, ha="right", va="center")
    if left.bounds[0] >= left_limit:
        return left
    return label(text, (spec.nodes[idx], glyph[1] - gap), layout, L, va="top")


def node_labels(spec: BeamSpec, layout: Layout, supports_group: Group) -> Group:
    """Each node's label, centred under its node on a line below the lowest support."""
    L = spec.length
    fs = _font_size(layout, L)
    gap = layout.label_gap * fs
    by_node: dict[int, float] = {}
    supported = [i for i, k in enumerate(spec.supports) if k != "free"]
    for i, sup in zip(supported, supports_group.children):
        # Glyphs and any stiffness label placed under them.
        parts = [c for c in sup.children if not (isinstance(c, Shape) and c.is_empty)]
        by_node[i] = min(c.bounds[1] for c in parts)
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
        # Never shorter than two arrowheads, so a squeezed arrow keeps a shaft.
        h = max(scale.point(load.mag1), 2 * hl)
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
    last = len(spec.spans) - 1
    for i, ((a, b), text) in enumerate(zip(zip(spec.nodes, spec.nodes[1:]), spec.span_labels)):
        parts.append(_span_label(text, a, b, y, i == 0, i == last, layout, L))
    if len(spec.spans) > 1:
        y -= layout.dimension_spacing * L
        parts.append(Shape(geometry=glyphs.dimension_line([spec.nodes[0], spec.nodes[-1]], y, tick), **style))
        parts.append(label(spec.length_label, ((spec.nodes[0] + spec.nodes[-1]) / 2, y + gap), layout, L))
    return group(parts, role="dimensions")


def _span_label(text: str, a: float, b: float, y: float, first: bool, last: bool,
                layout: Layout, L: float) -> Text:
    """
    A span's dimension: centred above its line, or, when it is wider than the
    span, beyond the line's end (end spans) or under the line (inner spans).
    """
    gap = layout.label_gap * _font_size(layout, L)
    above = label(text, ((a + b) / 2, y + gap), layout, L)
    width = above.bounds[2] - above.bounds[0]
    if width <= (b - a) - 2 * gap or (first and last):
        return above
    if last:
        return label(text, (b + gap, y + gap), layout, L, ha="left")
    if first:
        return label(text, (a - gap, y + gap), layout, L, ha="right")
    return label(text, ((a + b) / 2, y - gap), layout, L, va="top")


def _legend_title(spec: BeamSpec, layout: Layout) -> str:
    return layout.legend_title or (
        "Load cases & occupancies" if any(k.kind == "occupancy" for k in spec.keys) else "Load cases"
    )


def _legend_key(spec: BeamSpec, layout: Layout, i: int, x: float, y: float) -> list:
    """Key 'i' as a swatch and its name, with the swatch's left edge at x, centred on y."""
    L = spec.length
    fs = _font_size(layout, L)
    s = layout.swatch_size * L
    key, color = spec.keys[i], layout.color(i)
    return [
        Shape(geometry=glyphs.swatch(x, y - s / 2, s), fill_color=color, fill_opacity=0.6,
              stroke_color=color, stroke_width=layout.stroke_width, z=Z_TEXT, key=key.name),
        label(key.name, (x + s + 0.6 * fs, y), layout, L, ha="left", va="center", key=key.name),
    ]


def legend(spec: BeamSpec, layout: Layout, drawing: Bounds, position: str = "right") -> Group:
    """
    The legend keys. On the "right", a column aligned to the drawing's top. On
    "top", rows above the drawing, starting at its left edge: the title, then
    the keys, wrapping to a new row where a row would pass the drawing's right
    edge.
    """
    if not spec.keys:
        return group(role="legend")
    if position == "top":
        return _legend_top(spec, layout, drawing)
    L = spec.length
    fs = _font_size(layout, L)
    x = drawing[2] + layout.legend_gap * L
    parts = [label(_legend_title(spec, layout), (x, drawing[3]), layout, L, ha="left", va="top")]
    pitch = layout.legend_row * fs
    y = drawing[3] - pitch * 1.5
    for i in range(len(spec.keys)):
        parts += _legend_key(spec, layout, i, x, y)
        y -= pitch
    return group(parts, role="legend")


def _legend_top(spec: BeamSpec, layout: Layout, drawing: Bounds) -> Group:
    L = spec.length
    fs = _font_size(layout, L)
    gap = layout.legend_item_gap * fs
    left, right = drawing[0], max(drawing[2], drawing[0])
    title = label(_legend_title(spec, layout), (0, 0), layout, L, ha="left", va="center")
    items = [[title]] + [_legend_key(spec, layout, i, 0, 0) for i in range(len(spec.keys))]

    rows: list[list[list]] = [[]]
    x = left
    for item in items:
        width = group(item).bounds[2]
        if rows[-1] and x + width > right:
            rows.append([])
            x = left
        rows[-1].append(translate(group(item), dx=x))
        x += width + gap

    # Rows from the bottom up, so the lowest sits 'legend_top_gap' above the drawing.
    pitch = layout.legend_row * fs
    parts = []
    y = drawing[3] + layout.legend_top_gap * L + layout.swatch_size * L / 2
    for row in reversed(rows):
        parts += [translate(item, dy=y) for item in row]
        y += pitch
    return group(parts, role="legend")


# --- Whole diagram -------------------------------------------------------------------


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


def beam_diagram(obj, layout: Optional[Layout] = None, beam_id: Optional[str] = None,
                 aspect: Optional[float] = None, margin: float = 0.02,
                 width: Optional[float] = None) -> Group:
    """
    Returns the free-body diagram of a beam as one Group: load bands above the
    beam, supports and node labels, dimensions below, and the legend. 'obj' is
    anything `as_spec` accepts.

    With 'aspect' (target width / height), the diagram is arranged to fill a
    box of that shape as fully as it can. The vertical proportions are
    stretched within `layout.stretch` toward the target shape and, with
    `legend_position="auto"`, the legend goes on top when that leaves the
    diagram larger than a legend on the right. 'margin' is the renderer's
    margin (× drawing width), counted in the fit.

    'width' is the output width in points. With it and `layout.font_size_pt`,
    the text is sized in points: the diagram is arranged again until its text
    comes out at that size in the output. Symbols (supports, arrowheads,
    legend swatches) scale with the text.
    """
    spec = as_spec(obj, beam_id)
    layout = layout or Layout()
    if width is None or layout.font_size_pt is None:
        return _arrange(spec, layout, aspect, margin)
    if width <= 0:
        raise ValueError(f"width must be positive, got {width}")
    # The text's size in the output depends on the drawing's extent, which
    # depends on the text (labels, legend). A few fixed-point steps settle it.
    # Symbols (supports, arrowheads, swatches) scale with the text.
    factor = 1.0
    for _ in range(8):
        scaled = layout.text_scaled(factor)
        diagram = _arrange(spec, scaled, aspect, margin)
        x0, _, x1, _ = frame(diagram.bounds, margin, aspect)
        points = scaled.font_size * spec.length * width / (x1 - x0)
        if abs(points - layout.font_size_pt) <= 0.005 * layout.font_size_pt:
            break
        factor *= layout.font_size_pt / points
    return diagram


def _arrange(spec: BeamSpec, layout: Layout, aspect: Optional[float], margin: float) -> Group:
    """The diagram for 'layout', fitted to 'aspect' if given."""
    if aspect is None:
        position = "top" if layout.legend_position == "top" else "right"
        return _compose(spec, layout, position)
    if aspect <= 0:
        raise ValueError(f"aspect must be positive, got {aspect}")
    if layout.legend and spec.keys and layout.legend_position == "auto":
        positions = ["right", "top"]
    else:
        positions = ["top" if layout.legend_position == "top" else "right"]
    # The larger the fitted scale, the larger the drawing (and its text) in the
    # box. The first position wins ties, so "right" is kept unless "top" is
    # clearly better.
    best_scale, best = _fit(spec, layout, positions[0], aspect, margin)
    for position in positions[1:]:
        scale, diagram = _fit(spec, layout, position, aspect, margin)
        if scale > best_scale * 1.01:
            best_scale, best = scale, diagram
    return best


def fitted_scale(bounds: Bounds, aspect: float, margin: float = 0.02) -> float:
    """
    Returns the scale at which 'bounds', with 'margin' × its width on every
    side, fits a box 'aspect' wide and 1 high.
    """
    w, h = bounds[2] - bounds[0], bounds[3] - bounds[1]
    pad = 2 * margin * w
    return min(aspect / (w + pad), 1 / (h + pad))


def _fit(spec: BeamSpec, layout: Layout, position: str, aspect: float, margin: float):
    """
    Returns (fitted scale, diagram) for the stretch, within `layout.stretch`,
    that brings the diagram's shape closest to 'aspect'. Taller is lower
    width / height, and stretching only makes a diagram taller, so the
    search is a bracketed root find on the shape.
    """
    def build(f: float):
        diagram = _compose(spec, layout.stretched(f), position)
        return _shape(diagram.bounds, margin) - aspect, diagram

    lo, hi = layout.stretch
    g_lo, d_lo = build(lo)
    if g_lo <= 0 or lo == hi:  # Too tall even at the least stretch.
        return fitted_scale(d_lo.bounds, aspect, margin), d_lo
    g_hi, d_hi = build(hi)
    if g_hi >= 0:  # Too wide even at the most stretch.
        return fitted_scale(d_hi.bounds, aspect, margin), d_hi
    best = d_lo
    for _ in range(12):
        # Regula falsi with the Illinois tweak: the shape is close to linear in f.
        f = hi - g_hi * (hi - lo) / (g_hi - g_lo)
        g, best = build(f)
        if abs(g) <= 0.005 * aspect:
            break
        if g > 0:
            lo, g_lo = f, g
            g_hi /= 2
        else:
            hi, g_hi = f, g
            g_lo /= 2
    return fitted_scale(best.bounds, aspect, margin), best


def _shape(bounds: Bounds, margin: float) -> float:
    """Width / height of 'bounds' with the renderer's margin added."""
    w, h = bounds[2] - bounds[0], bounds[3] - bounds[1]
    pad = 2 * margin * w
    return (w + pad) / (h + pad)


def _compose(spec: BeamSpec, layout: Layout, position: str) -> Group:
    beam = beam_line(spec, layout)
    sup = supports(spec, layout)
    labels = node_labels(spec, layout, sup)
    loads = load_bands(spec, layout, base=_half_depth(spec))
    below = [g.bounds[1] for g in (sup, labels) if len(g)]
    lowest = min([*below, -_half_depth(spec)])
    dims = dimensions(spec, layout, top=lowest)
    parts = [loads, beam, sup, labels, dims]
    if layout.legend:
        parts.append(legend(spec, layout, group(parts).bounds, position))
    return group(parts, role="diagram")
