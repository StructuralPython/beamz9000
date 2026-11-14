"""
Renders elements with matplotlib: PNG, PDF, SVG (and anything else
matplotlib can save) from the file suffix.

Shapes become PathPatches. Texts become matplotlib Text artists, so they stay
text: selectable and searchable in PDF (TrueType embedded) and SVG (<text>).
Text is drawn from the font file the layout measured with, positioned at its
measured baseline start, and sized so its em height equals `font_size`
drawing units. Labels therefore land exactly where layout reserved space.

The figure is sized from the drawing: `width` inches across the drawing plus
margins, with the height following the drawing's proportions. The Agg
canvas is used directly (no pyplot), so this is safe in scripts, servers and
notebooks.
"""

from __future__ import annotations

import io
import math
import pathlib
from typing import Optional, Union

import matplotlib as mpl
import numpy as np
import shapely
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import to_rgba
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.patches import PathPatch
from matplotlib.path import Path
from pydantic import BaseModel, ConfigDict, Field
from shapely.geometry.base import BaseGeometry

from beamz9000.graphics import text as shaping
from beamz9000.render.frame import frame
from beamz9000.graphics.elements import Element, Shape, Text, flatten

_DASHES = {"solid": "solid", "dashed": (0, (6, 4)), "dotted": (0, (1, 3)), "dashdot": (0, (6, 3, 1, 3))}

# Keep text as text in vector output.
_RC = {"pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none", "hatch.linewidth": 0.6}


def geometry_path(geom: BaseGeometry) -> tuple[Optional[Path], bool]:
    """
    Returns (Path, closed) for any shapely geometry. 'closed' is True for
    polygonal geometry (which gets a face colour). Points are skipped.
    """
    verts, codes = [], []
    closed = False

    def add_ring(coords, close):
        pts = np.asarray(coords)[:, :2]
        if len(pts) < 2:
            return
        verts.extend(pts.tolist())
        codes.extend([Path.MOVETO] + [Path.LINETO] * (len(pts) - 1))
        if close:
            verts.append(pts[0].tolist())
            codes.append(Path.CLOSEPOLY)

    def walk(g):
        nonlocal closed
        if g.is_empty:
            return
        kind = g.geom_type
        if kind == "Polygon":
            closed = True
            g = shapely.geometry.polygon.orient(g, sign=1.0)  # CCW shell, CW holes.
            for ring in [g.exterior, *g.interiors]:
                add_ring(ring.coords, True)
        elif kind in ("LineString", "LinearRing"):
            add_ring(g.coords, False)
        elif kind.startswith("Multi") or kind == "GeometryCollection":
            for part in g.geoms:
                walk(part)

    walk(geom)
    if not verts:
        return None, closed
    return Path(np.array(verts), codes), closed


def _rgba(color, opacity):
    return "none" if color is None else to_rgba(color, opacity)


class MatplotlibRenderer(BaseModel):
    """Render settings. `width` is the figure width in inches."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    width: float = Field(12.0, gt=0)
    dpi: float = Field(150.0, gt=0)
    height: Optional[float] = Field(
        None, gt=0,
        description="Output height, in inches like width. None follows the drawing's shape; "
        "otherwise the output is exactly width × height, with the drawing scaled to fit and centred.",
    )
    margin: float = Field(0.02, ge=0, description="Margin around the drawing, × drawing width.")
    background: Optional[str] = "white"

    def figure(self, element: Element) -> Figure:
        """Returns a matplotlib Figure with 'element' drawn on it."""
        leaves = flatten(element)
        x0, y0, x1, y1 = frame(element.bounds, self.margin, self.aspect)
        height = self.height or self.width * (y1 - y0) / (x1 - x0)
        fig = Figure(figsize=(self.width, height), dpi=self.dpi, facecolor=self.background or "none")
        FigureCanvasAgg(fig)
        ax = fig.add_axes((0, 0, 1, 1))
        ax.set_axis_off()
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
        ax.set_aspect("equal", adjustable="box")
        points_per_unit = self.width * 72 / (x1 - x0)
        for leaf in leaves:
            if isinstance(leaf, Shape):
                self._draw_shape(ax, leaf)
            else:
                self._draw_text(ax, leaf, points_per_unit)
        return fig

    def _draw_shape(self, ax, s: Shape) -> None:
        path, closed = geometry_path(s.geometry)
        if path is None:
            return
        face = _rgba(s.fill_color, s.fill_opacity) if closed else "none"
        patch = PathPatch(
            path, facecolor=face, edgecolor=_rgba(s.stroke_color, s.stroke_opacity),
            linewidth=s.stroke_width if s.stroke_color is not None else 0,
            linestyle=_DASHES[s.line_type], zorder=s.z, capstyle="round", joinstyle="round",
        )
        if s.hatch and closed:
            patch.set_hatch(s.hatch)
            patch.set_hatchcolor(_rgba(s.stroke_color or "black", s.stroke_opacity))
        ax.add_patch(patch)

    def _draw_text(self, ax, t: Text, points_per_unit: float) -> None:
        dx, dy = shaping.baseline_offset(t)
        angle = math.radians(t.rotation)
        x = t.anchor[0] + dx * math.cos(angle) - dy * math.sin(angle)
        y = t.anchor[1] + dx * math.sin(angle) + dy * math.cos(angle)
        props = FontProperties(fname=shaping.font_path(t.font_family, t.font_weight, t.font_style))
        ax.text(
            x, y, t.text, fontproperties=props, fontsize=t.font_size * points_per_unit,
            color=_rgba(t.fill_color, t.fill_opacity), ha="left", va="baseline",
            rotation=t.rotation, rotation_mode="anchor", zorder=t.z, parse_math=False,
        )

    def to_bytes(self, element: Element, format: str = "png") -> bytes:
        """Returns 'element' rendered in 'format' (png, pdf, svg, ...)."""
        buf = io.BytesIO()
        with mpl.rc_context(_RC):
            self.figure(element).savefig(buf, format=format, dpi=self.dpi, facecolor=self.background or "none")
        return buf.getvalue()

    def save(self, element: Element, path: Union[str, pathlib.Path]) -> pathlib.Path:
        """Saves 'element' to 'path'; the suffix picks the format."""
        path = pathlib.Path(path)
        path.write_bytes(self.to_bytes(element, format=path.suffix.lstrip(".").lower() or "png"))
        return path

    @property
    def aspect(self) -> Optional[float]:
        """Width / height of the output when 'height' is set, else None."""
        return None if self.height is None else self.width / self.height

    @property
    def width_pt(self) -> float:
        """The output width in points ('width' is in inches)."""
        return self.width * 72
