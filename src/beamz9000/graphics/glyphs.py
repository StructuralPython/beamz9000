"""
Glyph functions: small, pure functions that return shapely geometry.

Following fbd_plotting's glyphs.py, each glyph is composed from single-purpose
functions with the same proportions (support height and width = half the glyph
width, four ground ticks one fifth of the glyph width deep at 45°). Where
fbd_plotting multiplied `horz`/`vert` flags through every coordinate, these
glyphs are drawn once at the origin in a standard orientation, then `orient()`
rotates and `place()` moves them, so any direction works.

Conventions: y is up. A support glyph's origin is the point where the beam
meets it, with the support drawn below. Arrows point from tail to tip.
"""

from __future__ import annotations

import math
from typing import Literal, Optional

import numpy as np
import shapely
from shapely import LineString, MultiLineString, MultiPolygon, Point, Polygon, affinity
from shapely.geometry.base import BaseGeometry

Facing = Literal["up", "down", "left", "right"]
SupportKind = Literal["pin", "roller", "fixed", "free", "spring", "rotational_spring"]

EMPTY = shapely.GeometryCollection()

# --- Orientation ------------------------------------------------------------------

_FACING_ANGLE = {"up": 0.0, "right": -90.0, "down": 180.0, "left": 90.0}


def orient(geom: BaseGeometry, facing: Facing = "up") -> BaseGeometry:
    """
    Returns 'geom', drawn for an element above the origin ("up"), turned to
    support an element in the 'facing' direction: "right" puts the glyph left
    of the origin (a wall at a beam's left end), "left" puts it to the right.
    """
    angle = _FACING_ANGLE[facing]
    return affinity.rotate(geom, angle, origin=(0, 0)) if angle else geom


def place(geom: BaseGeometry, anchor: tuple[float, float] = (0.0, 0.0), facing: Facing = "up") -> BaseGeometry:
    """Returns 'geom' oriented to 'facing', then moved so its origin is at 'anchor'."""
    return affinity.translate(orient(geom, facing), *anchor)


# --- Support proportions (from fbd_plotting) ------------------------------------------


def support_height(gw: float) -> float:
    """The height of a support body for glyph width 'gw'."""
    return gw / 2


def support_width(gw: float) -> float:
    """The width of a support body for glyph width 'gw'."""
    return gw / 2


def ground_elevation(gw: float) -> float:
    """The y of the ground line below the origin."""
    return -support_height(gw)


def tick_depth(gw: float) -> float:
    """The depth of the ground ticks (an arbitrary ratio, as in fbd_plotting)."""
    return gw / 5


# --- Support parts -------------------------------------------------------------------


def pin_body(gw: float) -> Polygon:
    """A triangle with its apex at the origin and its base on the ground."""
    sw, ge = support_width(gw), ground_elevation(gw)
    return Polygon([(-sw / 2, ge), (0.0, 0.0), (sw / 2, ge)])


def roller_body(gw: float, resolution: int = 16) -> Polygon:
    """A circle touching the origin at its top and the ground at its bottom."""
    sh = support_height(gw)
    return Point(0.0, -sh / 2).buffer(sh / 2, quad_segs=resolution)


def fixed_body(gw: float, width: Optional[float] = None) -> Polygon:
    """
    A block between the origin and the ground. 'width' (along the ground)
    defaults to the support width; a wider block covers a deep beam's end
    without growing the rest of the glyph.
    """
    sw, ge = width or support_width(gw), ground_elevation(gw)
    return shapely.box(-sw / 2, ge, sw / 2, 0.0)


def ground_line(gw: float, width: Optional[float] = None) -> LineString:
    """The ground line under a support, 'width' long (default: one glyph width)."""
    ge, w = ground_elevation(gw), width or gw
    return LineString([(-w / 2, ge), (w / 2, ge)])


def ground_ticks(gw: float, n_ticks: int = 4, width: Optional[float] = None) -> MultiLineString:
    """'n_ticks' 45° hatch ticks hanging below a ground line 'width' long."""
    ge, td, w = ground_elevation(gw), tick_depth(gw), width or gw
    spacing = w / (n_ticks - 1)
    ticks = []
    for i in range(n_ticks):
        x1 = -w / 2 + i * spacing
        ticks.append(LineString([(x1 - td, ge - td), (x1, ge)]))
    return MultiLineString(ticks)


def ground(gw: float, n_ticks: int = 4, width: Optional[float] = None) -> MultiLineString:
    """The ground line and its ticks, as one geometry."""
    return MultiLineString([ground_line(gw, width), *ground_ticks(gw, n_ticks, width).geoms])


def spring_coil(gw: float, coils: int = 3, lead: float = 0.15) -> LineString:
    """
    A zigzag spring from the origin down to the ground, with short straight
    leads ('lead' × height) at each end.
    """
    sh, sw = support_height(gw), support_width(gw)
    top, bottom = -lead * sh, -(1 - lead) * sh
    pts = [(0.0, 0.0), (0.0, top)]
    n = 2 * coils
    for i in range(n):
        y = top + (bottom - top) * (i + 0.5) / n
        pts.append((sw / 2 if i % 2 == 0 else -sw / 2, y))
    pts += [(0.0, bottom), (0.0, -sh)]
    return LineString(pts)


def spiral(r_inner: float, r_outer: float, turns: float = 1.75, segments: int = 64,
           start: float = 90.0) -> LineString:
    """An Archimedean spiral about the origin, winding outward counter-clockwise."""
    t = np.linspace(0.0, 1.0, segments)
    r = r_inner + (r_outer - r_inner) * t
    a = np.radians(start) + 2 * np.pi * turns * t
    return LineString(np.column_stack([r * np.cos(a), r * np.sin(a)]))


def rotational_spring_coil(gw: float) -> LineString:
    """The spiral of a rotational spring, wound about the origin."""
    return spiral(0.06 * gw, 0.36 * gw)


_BODIES = {"pin": pin_body, "roller": roller_body, "fixed": fixed_body, "rotational_spring": pin_body}


def support(kind: SupportKind, gw: float, n_ticks: int = 4,
            width: Optional[float] = None) -> tuple[BaseGeometry, BaseGeometry]:
    """
    Returns (body, strokes) for a support of 'kind' at the origin. They are
    kept apart so each can be styled on its own: a filled body, and stroked
    lines (the ground, plus any spring coil). A "free" end returns two empty
    geometries; a "spring" has no filled body.

    'width' stretches the ground (and a fixed block, to width - gw/2) without
    growing the glyph's height or ticks; extra ticks keep their spacing.
    """
    if kind == "free":
        return EMPTY, EMPTY
    if width is not None and width > gw:
        n_ticks = max(n_ticks, round((n_ticks - 1) * width / gw) + 1)
    else:
        width = None
    lines = list(ground(gw, n_ticks, width).geoms)
    if kind == "spring":
        return Polygon(), MultiLineString([spring_coil(gw), *lines])
    if kind == "rotational_spring":
        lines.append(rotational_spring_coil(gw))
    if kind == "fixed":
        return fixed_body(gw, width - gw / 2 if width else None), MultiLineString(lines)
    return _BODIES[kind](gw), MultiLineString(lines)


def support_depth(gw: float) -> float:
    """How far a support glyph reaches below the origin, ticks included."""
    return support_height(gw) + tick_depth(gw)


# --- Arrows --------------------------------------------------------------------------


def arrow_head(tip: tuple[float, float], direction: tuple[float, float],
               length: float, width: float) -> Polygon:
    """A triangular head with its point at 'tip', pointing along 'direction'."""
    ux, uy = _unit(direction)
    bx, by = tip[0] - ux * length, tip[1] - uy * length
    px, py = -uy * width / 2, ux * width / 2
    return Polygon([tip, (bx + px, by + py), (bx - px, by - py)])


def arrow(tail: tuple[float, float], tip: tuple[float, float],
          head_length: float, head_width: float) -> tuple[LineString, Polygon]:
    """
    Returns (shaft, head) for an arrow from 'tail' to 'tip'. The shaft stops at
    the head's base. An arrow shorter than its head is drawn as a head scaled to
    its length, with an empty shaft.
    """
    dx, dy = tip[0] - tail[0], tip[1] - tail[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return LineString(), Polygon()
    if length <= head_length:
        ratio = length / head_length
        return LineString(), arrow_head(tip, (dx, dy), length, head_width * ratio)
    ux, uy = dx / length, dy / length
    base = (tip[0] - ux * head_length, tip[1] - uy * head_length)
    return LineString([tail, base]), arrow_head(tip, (dx, dy), head_length, head_width)


def moment_arc(radius: float, ccw: bool, head_length: float, head_width: float,
               sweep: float = 270.0, segments: int = 48) -> tuple[LineString, Polygon]:
    """
    Returns (arc, head) for a moment symbol centred on the origin. The arc opens
    at the bottom and the head shows the direction: counter-clockwise when
    'ccw' is True.
    """
    start = -90.0 + (360.0 - sweep) / 2 if ccw else -90.0 - (360.0 - sweep) / 2
    sign = 1.0 if ccw else -1.0
    end = start + sign * sweep
    # The shaft stops where the head's base begins, measured along the arc.
    head_angle = math.degrees(head_length / radius)
    shaft_end = end - sign * head_angle
    angles = np.radians(np.linspace(start, shaft_end, segments))
    arc = LineString(np.column_stack([radius * np.cos(angles), radius * np.sin(angles)]))
    tip = (radius * math.cos(math.radians(end)), radius * math.sin(math.radians(end)))
    base = arc.coords[-1]
    head = arrow_head(tip, (tip[0] - base[0], tip[1] - base[1]), head_length, head_width)
    return arc, head


# --- Line loads ----------------------------------------------------------------------


def trapezoid(x1: float, x2: float, h1: float, h2: float, base: float = 0.0) -> Polygon:
    """The region of a line load: from 'base' up to heights h1 at x1 and h2 at x2."""
    return Polygon([(x1, base), (x2, base), (x2, base + h2), (x1, base + h1)])


def arrow_stations(x1: float, x2: float, spacing: float, min_arrows: int = 2) -> np.ndarray:
    """Evenly spaced x positions from x1 to x2, about 'spacing' apart, ends included."""
    n = max(min_arrows, int(round((x2 - x1) / spacing)) + 1)
    return np.linspace(x1, x2, n)


def line_load_arrows(x1: float, x2: float, h1: float, h2: float, spacing: float,
                     head_length: float, head_width: float, base: float = 0.0,
                     upward: bool = False) -> tuple[MultiLineString, MultiPolygon]:
    """
    Returns (shafts, heads) for arrows across a line load region. Downward
    arrows run from the top edge to the base; 'upward' arrows from the base to
    the top edge.
    """
    shafts, heads = [], []
    for x in arrow_stations(x1, x2, spacing):
        h = h1 + (h2 - h1) * ((x - x1) / (x2 - x1) if x2 != x1 else 0.0)
        top, bottom = (x, base + h), (x, base)
        tail, tip = (bottom, top) if upward else (top, bottom)
        shaft, head = arrow(tail, tip, head_length, head_width)
        if not shaft.is_empty:
            shafts.append(shaft)
        if not head.is_empty:
            heads.append(head)
    return MultiLineString(shafts), MultiPolygon(heads)


def hatch_lines(region: Polygon, spacing: float, angle: float = 45.0) -> MultiLineString:
    """
    Returns parallel lines at 'angle' degrees, 'spacing' apart, clipped to
    'region': hatching as geometry, for media without hatch patterns.
    """
    minx, miny, maxx, maxy = region.bounds
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    r = math.hypot(maxx - minx, maxy - miny) / 2 + spacing
    lines = [LineString([(cx - r, cy + o), (cx + r, cy + o)]) for o in np.arange(-r, r + spacing, spacing)]
    field = affinity.rotate(MultiLineString(lines), angle, origin=(cx, cy))
    clipped = field.intersection(region)
    parts = [g for g in getattr(clipped, "geoms", [clipped]) if isinstance(g, LineString) and not g.is_empty]
    return MultiLineString(parts)


# --- Dimensions ------------------------------------------------------------------------


def dimension_tick(x: float, y: float, size: float) -> MultiLineString:
    """An architectural tick at (x, y): a 45° slash and a short extension line."""
    s = size / 2
    return MultiLineString([
        [(x - s, y - s), (x + s, y + s)],
        [(x, y - size), (x, y + size)],
    ])


def dimension_line(xs: list[float], y: float, tick_size: float) -> MultiLineString:
    """A chained dimension line at 'y' through the stations 'xs', ticked at each one."""
    xs = sorted(xs)
    parts = [LineString([(xs[0], y), (xs[-1], y)])]
    for x in xs:
        parts.extend(dimension_tick(x, y, tick_size).geoms)
    return MultiLineString(parts)


def swatch(x: float, y: float, size: float) -> Polygon:
    """A legend swatch: a square with its lower-left corner at (x, y)."""
    return shapely.box(x, y, x + size, y + size)


def _unit(v: tuple[float, float]) -> tuple[float, float]:
    n = math.hypot(*v)
    if n == 0:
        raise ValueError("an arrow direction cannot be zero")
    return v[0] / n, v[1] / n
