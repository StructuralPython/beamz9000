"""
Renders elements as standalone SVG.

Shapes become <path> elements; Texts become <text>, so labels stay searchable
and selectable. Text is placed at its measured baseline start (the same
libraqm measurement layout used), so alignment does not depend on the viewer's
text-anchor support. Hatches become <pattern> fills drawn over the fill colour.

The drawing's y-up coordinates are flipped once (y -> -y), so text is never
mirrored.

Viewers draw <text> with whatever font they find for `font-family`. With
`embed_font=True` the measured font file is embedded with @font-face, so every
viewer draws exactly the measured glyphs (at the cost of file size).
"""

from __future__ import annotations

import base64
import math
import pathlib
from typing import Optional, Union
from xml.sax.saxutils import escape, quoteattr

from matplotlib.colors import to_hex
from pydantic import BaseModel, ConfigDict, Field
from shapely.geometry.base import BaseGeometry

from beamz9000.graphics import text as shaping
from beamz9000.render.frame import frame
from beamz9000.graphics.elements import Element, Shape, Text, flatten

_DASHES = {"solid": None, "dashed": "6 4", "dotted": "1 3", "dashdot": "6 3 1 3"}
# Hatch characters -> line angles (degrees, y-up), as matplotlib reads them.
_HATCH_ANGLES = {"/": [45], "\\": [-45], "-": [0], "|": [90], "x": [45, -45], "X": [45, -45], "+": [0, 90]}


def _num(v: float) -> str:
    return f"{v:.6g}"


def path_data(geom: BaseGeometry) -> tuple[str, bool]:
    """Returns (SVG path data with y flipped, closed) for any shapely geometry."""
    parts: list[str] = []
    closed = False

    def ring(coords, close):
        pts = list(coords)
        if len(pts) < 2:
            return
        d = "M" + " L".join(f"{_num(x)},{_num(-y)}" for x, y, *_ in pts)
        parts.append(d + (" Z" if close else ""))

    def walk(g):
        nonlocal closed
        if g.is_empty:
            return
        kind = g.geom_type
        if kind == "Polygon":
            closed = True
            for r in [g.exterior, *g.interiors]:
                ring(r.coords, True)
        elif kind in ("LineString", "LinearRing"):
            ring(g.coords, False)
        elif kind.startswith("Multi") or kind == "GeometryCollection":
            for p in g.geoms:
                walk(p)

    walk(geom)
    return " ".join(parts), closed


def _color(c: Optional[str]) -> str:
    return "none" if c is None else to_hex(c)


class SVGRenderer(BaseModel):
    """SVG render settings. `width` is the output width in CSS pixels."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    width: float = Field(1200.0, gt=0)
    height: Optional[float] = Field(
        None, gt=0,
        description="Output height, in CSS pixels like width. None follows the drawing's shape; "
        "otherwise the output is exactly width × height, with the drawing scaled to fit and centred.",
    )
    margin: float = Field(0.02, ge=0, description="Margin around the drawing, × drawing width.")
    background: Optional[str] = "white"
    hatch_spacing: float = Field(0.012, gt=0, description="Hatch line spacing, × drawing width.")
    embed_font: bool = False

    def to_string(self, element: Element) -> str:
        leaves = flatten(element)
        x0, y0, x1, y1 = frame(element.bounds, self.margin, self.aspect)
        w, h = x1 - x0, y1 - y0
        px_per_unit = self.width / w
        defs: dict[tuple, tuple[str, str]] = {}  # key -> (id, xml)
        body = []
        if self.background:
            body.append(f'<rect x="{_num(x0)}" y="{_num(-y1)}" width="{_num(w)}" height="{_num(h)}" '
                        f'fill="{_color(self.background)}"/>')
        for leaf in leaves:
            if isinstance(leaf, Shape):
                body.extend(self._shape(leaf, defs, w, px_per_unit))
            else:
                body.append(self._text(leaf))
        style = self._font_faces(leaves) if self.embed_font else ""
        head = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{_num(self.width)}" '
            f'height="{_num(self.height or self.width * h / w)}" viewBox="{_num(x0)} {_num(-y1)} {_num(w)} {_num(h)}">'
        )
        defs_xml = "<defs>" + style + "".join(xml for _, xml in defs.values()) + "</defs>" if (defs or style) else ""
        return "\n".join([head, defs_xml, *body, "</svg>"])

    def _shape(self, s: Shape, defs: dict, drawing_width: float, px_per_unit: float) -> list[str]:
        d, closed = path_data(s.geometry)
        if not d:
            return []
        stroke = _color(s.stroke_color)
        attrs = [f'd="{d}"']
        attrs.append(f'fill="{_color(s.fill_color) if closed else "none"}"')
        if closed and s.fill_color is not None and s.fill_opacity < 1:
            attrs.append(f'fill-opacity="{_num(s.fill_opacity)}"')
        attrs.append(f'stroke="{stroke}"')
        if s.stroke_color is not None:
            # Stroke widths are points; 1 pt = 4/3 CSS px, converted to drawing units.
            attrs.append(f'stroke-width="{_num(s.stroke_width * 4 / 3 / px_per_unit)}"')
            attrs.append('stroke-linecap="round" stroke-linejoin="round"')
            if s.stroke_opacity < 1:
                attrs.append(f'stroke-opacity="{_num(s.stroke_opacity)}"')
            if _DASHES[s.line_type]:
                dash = " ".join(_num(float(v) * s.stroke_width * 4 / 3 / px_per_unit) for v in _DASHES[s.line_type].split())
                attrs.append(f'stroke-dasharray="{dash}"')
        out = [f'<path {" ".join(attrs)}/>']
        if closed and s.hatch:
            pid = self._hatch_pattern(s, defs, drawing_width, px_per_unit)
            out.append(f'<path d="{d}" fill="url(#{pid})" stroke="none"/>')
        return out

    def _hatch_pattern(self, s: Shape, defs: dict, drawing_width: float, px_per_unit: float) -> str:
        color = _color(s.stroke_color or "black")
        key = ("hatch", s.hatch, color, s.stroke_opacity)
        if key in defs:
            return defs[key][0]
        pid = f"hatch{len(defs)}"
        density = max(1, max(s.hatch.count(c) for c in set(s.hatch)))
        size = self.hatch_spacing * drawing_width / density
        lw = 0.6 * 4 / 3 / px_per_unit
        angles = sorted({a for c in s.hatch for a in _HATCH_ANGLES.get(c, [])}) or [45]
        lines = "".join(
            f'<pattern id="{pid}{i}" patternUnits="userSpaceOnUse" width="{_num(size)}" height="{_num(size)}" '
            f'patternTransform="rotate({_num(-a)})"><line x1="0" y1="0" x2="{_num(size)}" y2="0" '
            f'stroke="{color}" stroke-opacity="{_num(s.stroke_opacity)}" stroke-width="{_num(lw)}"/></pattern>'
            for i, a in enumerate(angles)
        )
        if len(angles) == 1:
            defs[key] = (pid, lines.replace(f'id="{pid}0"', f'id="{pid}"'))
        else:
            # Several angles: one pattern that paints each line pattern in turn.
            rects = "".join(f'<rect width="100%" height="100%" fill="url(#{pid}{i})"/>' for i in range(len(angles)))
            defs[key] = (pid, lines + f'<pattern id="{pid}" patternUnits="userSpaceOnUse" '
                         f'width="{_num(size)}" height="{_num(size)}">{rects}</pattern>')
        return pid

    def _text(self, t: Text) -> str:
        dx, dy = shaping.baseline_offset(t)
        a = math.radians(t.rotation)
        x = t.anchor[0] + dx * math.cos(a) - dy * math.sin(a)
        y = t.anchor[1] + dx * math.sin(a) + dy * math.cos(a)
        attrs = [
            f'x="{_num(x)}" y="{_num(-y)}"',
            f"font-family={quoteattr(t.font_family + ', sans-serif')}",
            f'font-size="{_num(t.font_size)}"',
            f'fill="{_color(t.fill_color)}"',
        ]
        if t.fill_opacity < 1:
            attrs.append(f'fill-opacity="{_num(t.fill_opacity)}"')
        if t.font_weight != "normal":
            attrs.append(f'font-weight="{t.font_weight}"')
        if t.font_style != "normal":
            attrs.append(f'font-style="{t.font_style}"')
        if t.rotation:
            attrs.append(f'transform="rotate({_num(-t.rotation)} {_num(x)} {_num(-y)})"')
        return f"<text {' '.join(attrs)}>{escape(t.text)}</text>"

    def _font_faces(self, leaves) -> str:
        seen, faces = set(), []
        for t in leaves:
            if not isinstance(t, Text):
                continue
            key = (t.font_family, t.font_weight, t.font_style)
            if key in seen:
                continue
            seen.add(key)
            data = base64.b64encode(pathlib.Path(shaping.font_path(*key)).read_bytes()).decode()
            faces.append(
                f"@font-face{{font-family:{quoteattr(t.font_family)[1:-1]!r};font-weight:{t.font_weight};"
                f"font-style:{t.font_style};src:url(data:font/ttf;base64,{data}) format('truetype');}}"
            )
        return "<style>" + "".join(faces) + "</style>" if faces else ""

    def to_bytes(self, element: Element, format: str = "svg") -> bytes:
        if format != "svg":
            raise ValueError("SVGRenderer only writes svg")
        return self.to_string(element).encode("utf-8")

    def save(self, element: Element, path: Union[str, pathlib.Path]) -> pathlib.Path:
        path = pathlib.Path(path)
        path.write_text(self.to_string(element), encoding="utf-8")
        return path

    @property
    def aspect(self) -> Optional[float]:
        """Width / height of the output when 'height' is set, else None."""
        return None if self.height is None else self.width / self.height

    @property
    def width_pt(self) -> float:
        """The output width in points ('width' is in CSS pixels (1 px = 0.75 pt))."""
        return self.width * 0.75
