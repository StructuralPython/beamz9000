"""
Text measurement with real shaping.

Text stays text: a `Text` element is drawn by each renderer as a native,
searchable text object (a matplotlib Text artist, an SVG <text>, ...), never as
outlines. What layout needs is the exact space a label will take, and that
comes from shaping it the way the renderer will.

Shaping is done by libraqm (HarfBuzz), which matplotlib 3.11+ bundles. It
applies kerning, ligatures, combining marks and complex-script rules, so the
measured advance matches what matplotlib (and any HarfBuzz-based viewer) draws
with the same font file.

Units: text is shaped at 1 em = 1 unit and scaled by `font_size` (drawing
units). Bounds use the advance width and the font's ascender/descender (the
line box), not the ink, so neighbouring labels share baselines and spacing.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import shapely
from matplotlib import _text_helpers, font_manager
from matplotlib.ft2font import FT2Font, LoadFlags
from shapely import affinity

# FreeType is asked for metrics at this many pixels per em; results are scaled to 1 em.
_PX_PER_EM = 100.0


@dataclass(frozen=True)
class TextExtent:
    """The size of a line of text, in drawing units at its font size."""

    advance: float  # Horizontal advance (layout width).
    ascent: float  # Font ascender above the baseline (positive).
    descent: float  # Font descender below the baseline (positive).
    cap_height: float  # Height of capital letters above the baseline.

    @property
    def height(self) -> float:
        return self.ascent + self.descent


@lru_cache(maxsize=None)
def font_path(family: str = "DejaVu Sans", weight: str = "normal", style: str = "normal") -> str:
    """
    Returns the font file matplotlib resolves for this family, weight and
    style. Renderers draw with this same file so drawn text matches the layout.
    """
    props = font_manager.FontProperties(family=family, weight=weight, style=style)
    return font_manager.findfont(props)


def _font(path: str) -> FT2Font:
    font = font_manager.get_font([path])
    font.set_size(_PX_PER_EM, 72)
    return font


@lru_cache(maxsize=4096)
def _advance(text: str, path: str) -> float:
    """Returns the shaped advance width of 'text' in em."""
    font = _font(path)
    advance = 0.0
    for item in _text_helpers.layout(text, font):
        glyph = item.ft_object.load_glyph(item.glyph_index, flags=LoadFlags.NO_HINTING)
        advance = max(advance, (item.x + glyph.linearHoriAdvance / 65536) / _PX_PER_EM)
    return advance


@lru_cache(maxsize=64)
def _font_metrics(path: str) -> tuple[float, float, float]:
    """Returns (ascender, descender, cap height) in em; descender positive."""
    font = _font(path)
    upem = font.units_per_EM
    ascender, descender = font.ascender / upem, -font.descender / upem
    os2 = font.get_sfnt_table("OS/2") or {}
    cap = os2.get("sCapHeight") or 0
    if cap:
        cap_height = cap / upem
    else:  # The font doesn't record a cap height: use the ink height of "H".
        font.set_text("H", 0.0, flags=LoadFlags.NO_HINTING)
        cap_height = (font.get_width_height()[1] - font.get_descent()) / 64 / _PX_PER_EM
    return ascender, descender, cap_height


def measure(text: str, font_size: float = 1.0, family: str = "DejaVu Sans",
            weight: str = "normal", style: str = "normal") -> TextExtent:
    """Returns the shaped size of 'text' at 'font_size' (drawing units)."""
    path = font_path(family, weight, style)
    ascender, descender, cap = _font_metrics(path)
    advance = _advance(text, path) if text else 0.0
    return TextExtent(advance * font_size, ascender * font_size, descender * font_size, cap * font_size)


def measure_text(t) -> TextExtent:
    """Returns the shaped size of a Text element."""
    return measure(t.text, t.font_size, t.font_family, t.font_weight, t.font_style)


def baseline_offset(t, extent: TextExtent | None = None) -> tuple[float, float]:
    """
    Returns the (dx, dy), in the text's own unrotated frame, from its anchor to
    the left end of its baseline, honouring `ha` and `va`. Renderers that place
    text by its baseline start (SVG, DXF) use this so every medium aligns
    text the same way.
    """
    extent = extent or measure_text(t)
    dx = {"left": 0.0, "center": -extent.advance / 2, "right": -extent.advance}[t.ha]
    dy = {
        "baseline": 0.0,
        "bottom": extent.descent,
        "top": -extent.ascent,
        "center": -extent.cap_height / 2,
    }[t.va]
    return dx, dy


def text_box(t) -> shapely.Polygon:
    """
    Returns the line box of a Text element (advance width × ascender to
    descender), aligned, rotated and placed. Layout reserves this box.
    """
    extent = measure_text(t)
    dx, dy = baseline_offset(t, extent)
    box = shapely.box(dx, dy - extent.descent, dx + extent.advance, dy + extent.ascent)
    if t.rotation:
        box = affinity.rotate(box, t.rotation, origin=(0, 0))
    return affinity.translate(box, *t.anchor)


def text_bounds(t) -> tuple[float, float, float, float]:
    """Returns the bounds of a Text element's line box."""
    return text_box(t).bounds
