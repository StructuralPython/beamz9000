"""
Renders elements with ReportLab: onto a canvas, as a platypus Flowable, or as
a standalone PDF.

Everything stays vector. Shapes become PDF paths, hatches are lines clipped
to their shape, and Texts are drawn with `drawString` in the same TrueType
font the layout measured, so labels are real, searchable PDF text. The font
is registered with ReportLab under a name derived from its file.

This is the renderer for documents built with ReportLab, such as ymprint
reports: `flowable()` returns an object that can go straight into a story.

Requires the `reportlab` extra: `uv add "beamz9000[reportlab]"`.
"""

from __future__ import annotations

import math
import pathlib
from typing import Optional, Union

import shapely
from matplotlib.colors import to_rgb
from pydantic import BaseModel, ConfigDict, Field
from reportlab.lib.colors import Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Flowable
from shapely.geometry.base import BaseGeometry

from beamz9000.graphics import text as shaping
from beamz9000.graphics.elements import Element, Shape, Text, flatten
from beamz9000.render.frame import frame, line_factor, line_weight

# Dash patterns, × the stroke width.
_DASHES = {"solid": None, "dashed": (6, 4), "dotted": (1, 3), "dashdot": (6, 3, 1, 3)}
# Hatch characters -> line angles (degrees, y-up), as matplotlib reads them.
_HATCH_ANGLES = {"/": [45], "\\": [-45], "-": [0], "|": [90], "x": [45, -45], "X": [45, -45], "+": [0, 90]}
_HATCH_WIDTH = 0.6  # pt


def register_font(family: str, weight: str = "normal", style: str = "normal") -> str:
    """
    Returns the ReportLab font name for a font, registering the TrueType file
    the layout measures with (found by matplotlib) the first time.
    """
    path = shaping.font_path(family, weight, style)
    name = "bz-" + pathlib.Path(path).stem
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(name, path))
    return name


def _color(value: Optional[str], opacity: float = 1.0) -> Optional[Color]:
    if value is None:
        return None
    r, g, b = to_rgb(value)
    return Color(r, g, b, alpha=opacity)


class _Transform:
    """Maps drawing units to points, with the frame's lower-left at (x, y)."""

    def __init__(self, bounds, scale: float, x: float, y: float):
        self.x0, self.y0 = bounds[0], bounds[1]
        self.k, self.x, self.y = scale, x, y

    def __call__(self, px: float, py: float) -> tuple[float, float]:
        return self.x + (px - self.x0) * self.k, self.y + (py - self.y0) * self.k


class ReportLabRenderer(BaseModel):
    """
    ReportLab render settings. `width` and `height` are in points. Without a
    height, the height follows the drawing's shape.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    width: float = Field(468.0, gt=0, description="Output width, in points (6.5 in by default).")
    height: Optional[float] = Field(
        None, gt=0,
        description="Output height, in points. None follows the drawing's shape; otherwise "
        "the output is exactly width × height, with the drawing scaled to fit and centred.",
    )
    margin: float = Field(0.02, ge=0, description="Margin around the drawing, × drawing width.")
    background: Optional[str] = None
    line_scale: Optional[float] = Field(
        None, gt=0,
        description="Factor on every line weight. None thins lines in proportion when the output "
        "is narrower than 12 in, so small images keep the proportions of large ones.",
    )
    hatch_spacing: float = Field(4.0, gt=0, description="Hatch line spacing, in points.")

    @property
    def aspect(self) -> Optional[float]:
        """Width / height of the output when 'height' is set, else None."""
        return None if self.height is None else self.width / self.height

    @property
    def width_pt(self) -> float:
        """The output width in points."""
        return self.width

    def size(self, element: Element) -> tuple[float, float]:
        """Returns the (width, height) in points that 'element' is drawn at."""
        x0, y0, x1, y1 = frame(element.bounds, self.margin, self.aspect)
        return self.width, self.height or self.width * (y1 - y0) / (x1 - x0)

    # --- Output ------------------------------------------------------------------

    def draw_on(self, canvas: Canvas, element: Element, x: float = 0.0, y: float = 0.0) -> None:
        """Draws 'element' on 'canvas' with its lower-left corner at (x, y), in points."""
        bounds = frame(element.bounds, self.margin, self.aspect)
        width, height = self.size(element)
        to_pt = _Transform(bounds, width / (bounds[2] - bounds[0]), x, y)
        canvas.saveState()
        if self.background:
            canvas.setFillColor(_color(self.background))
            canvas.rect(x, y, width, height, stroke=0, fill=1)
        for leaf in flatten(element):
            if isinstance(leaf, Shape):
                self._draw_shape(canvas, leaf, to_pt)
            else:
                self._draw_text(canvas, leaf, to_pt)
        canvas.restoreState()

    def flowable(self, element: Element) -> "DiagramFlowable":
        """Returns a platypus Flowable that draws 'element' at this renderer's size."""
        return DiagramFlowable(element, self)

    def to_bytes(self, element: Element) -> bytes:
        """Returns 'element' as a one-page PDF exactly the drawing's size."""
        import io

        buf = io.BytesIO()
        self._pdf(element, buf)
        return buf.getvalue()

    def save(self, element: Element, path: Union[str, pathlib.Path]) -> pathlib.Path:
        """Saves 'element' as a one-page PDF at 'path'."""
        path = pathlib.Path(path)
        if path.suffix.lower() != ".pdf":
            raise ValueError(f"the ReportLab renderer writes PDF, not {path.suffix or 'no suffix'}")
        path.write_bytes(self.to_bytes(element))
        return path

    def _pdf(self, element: Element, out) -> None:
        width, height = self.size(element)
        canvas = Canvas(out, pagesize=(width, height))
        self.draw_on(canvas, element)
        canvas.showPage()
        canvas.save()

    # --- Shapes ------------------------------------------------------------------

    def _draw_shape(self, canvas: Canvas, s: Shape, to_pt: _Transform) -> None:
        path, closed = _path(canvas, s.geometry, to_pt)
        if path is None:
            return
        fill = _color(s.fill_color, s.fill_opacity) if closed else None
        stroke = _color(s.stroke_color, s.stroke_opacity)
        canvas.saveState()
        if fill is not None:
            canvas.setFillColor(fill)
        if stroke is not None:
            canvas.setStrokeColor(stroke)
            sw = line_weight(s.stroke_width, line_factor(self.width_pt, self.line_scale))
            canvas.setLineWidth(sw)
            canvas.setLineCap(1)
            canvas.setLineJoin(1)
            dash = _DASHES[s.line_type]
            if dash:
                canvas.setDash([v * sw for v in dash])
        canvas.drawPath(path, stroke=int(stroke is not None), fill=int(fill is not None), fillMode=1)
        canvas.restoreState()
        if closed and s.hatch:
            self._hatch(canvas, s, to_pt)

    def _hatch(self, canvas: Canvas, s: Shape, to_pt: _Transform) -> None:
        """Hatch lines across the shape's bounding box, clipped to the shape."""
        clip, _ = _path(canvas, s.geometry, to_pt)
        x0, y0 = to_pt(*s.geometry.bounds[:2])
        x1, y1 = to_pt(*s.geometry.bounds[2:])
        cx, cy, r = (x0 + x1) / 2, (y0 + y1) / 2, math.hypot(x1 - x0, y1 - y0) / 2
        density = max(1, max(s.hatch.count(c) for c in set(s.hatch)))
        spacing = self.hatch_spacing / density
        angles = sorted({a for c in s.hatch for a in _HATCH_ANGLES.get(c, [])}) or [45]
        canvas.saveState()
        canvas.clipPath(clip, stroke=0, fill=0, fillMode=1)
        canvas.setStrokeColor(_color(s.stroke_color or "black", s.stroke_opacity))
        canvas.setLineWidth(line_weight(_HATCH_WIDTH, line_factor(self.width_pt, self.line_scale)))
        lines = []
        for angle in angles:
            a = math.radians(angle)
            ux, uy = math.cos(a), math.sin(a)  # Along the lines.
            nx, ny = -uy, ux  # Across them.
            n = int(r / spacing) + 1
            for i in range(-n, n + 1):
                ox, oy = cx + nx * i * spacing, cy + ny * i * spacing
                lines.append((ox - ux * r, oy - uy * r, ox + ux * r, oy + uy * r))
        canvas.lines(lines)
        canvas.restoreState()

    # --- Text --------------------------------------------------------------------

    def _draw_text(self, canvas: Canvas, t: Text, to_pt: _Transform) -> None:
        dx, dy = shaping.baseline_offset(t)
        a = math.radians(t.rotation)
        x, y = to_pt(t.anchor[0] + dx * math.cos(a) - dy * math.sin(a),
                     t.anchor[1] + dx * math.sin(a) + dy * math.cos(a))
        canvas.saveState()
        canvas.setFont(register_font(t.font_family, t.font_weight, t.font_style), t.font_size * to_pt.k)
        canvas.setFillColor(_color(t.fill_color, t.fill_opacity))
        canvas.translate(x, y)
        if t.rotation:
            canvas.rotate(t.rotation)
        canvas.drawString(0, 0, t.text)
        canvas.restoreState()


def _path(canvas: Canvas, geom: BaseGeometry, to_pt: _Transform):
    """Returns (ReportLab path, closed) for any shapely geometry; points are skipped."""
    path = canvas.beginPath()
    closed = False
    empty = True

    def ring(coords, close):
        nonlocal empty
        pts = [to_pt(x, y) for x, y, *_ in coords]
        if len(pts) < 2:
            return
        empty = False
        path.moveTo(*pts[0])
        for p in pts[1:]:
            path.lineTo(*p)
        if close:
            path.close()

    def walk(g):
        nonlocal closed
        if g.is_empty:
            return
        kind = g.geom_type
        if kind == "Polygon":
            closed = True
            g = shapely.geometry.polygon.orient(g, sign=1.0)
            for r in [g.exterior, *g.interiors]:
                ring(r.coords, True)
        elif kind in ("LineString", "LinearRing"):
            ring(g.coords, False)
        elif kind.startswith("Multi") or kind == "GeometryCollection":
            for part in g.geoms:
                walk(part)

    walk(geom)
    return (None if empty else path), closed


class DiagramFlowable(Flowable):
    """A diagram as a platypus Flowable, drawn at its renderer's size."""

    def __init__(self, element: Element, renderer: ReportLabRenderer):
        super().__init__()
        self.element = element
        self.renderer = renderer
        self.width, self.height = renderer.size(element)

    def wrap(self, avail_width, avail_height):
        return self.width, self.height

    def draw(self):
        self.renderer.draw_on(self.canv, self.element)
