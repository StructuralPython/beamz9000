"""The region of the drawing that a renderer's output shows."""

from __future__ import annotations

from typing import Optional

Bounds = tuple[float, float, float, float]


def frame(bounds: Bounds, margin: float, aspect: Optional[float] = None) -> Bounds:
    """
    Returns 'bounds' padded by 'margin' × its width on every side. With
    'aspect' (width / height), the padded region is then widened or heightened
    about its centre to that shape, so the drawing is centred in the output.
    """
    x0, y0, x1, y1 = bounds
    pad = margin * max(x1 - x0, 1e-12)
    x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    if aspect is None:
        return x0, y0, x1, y1
    w, h = x1 - x0, y1 - y0
    if w / h > aspect:
        grow = (w / aspect - h) / 2
        return x0, y0 - grow, x1, y1 + grow
    grow = (h * aspect - w) / 2
    return x0 - grow, y0, x1 + grow, y1


# Line weights in a Layout are set for an output this wide (12 in). In a
# narrower output every line is thinned in proportion, so a small image keeps
# the proportions of a large one: the beam does not swamp the drawing, and an
# arrow's shaft stays slim next to its head. Lines never go below the floor.
REFERENCE_WIDTH_PT = 864.0
MIN_LINE_PT = 0.25


def line_factor(width_pt: float, line_scale: Optional[float] = None) -> float:
    """
    The factor on every line weight for an output 'width_pt' wide: 'line_scale'
    if given, else width_pt / REFERENCE_WIDTH_PT, never more than 1.
    """
    if line_scale is not None:
        return line_scale
    return min(1.0, width_pt / REFERENCE_WIDTH_PT)


def line_weight(stroke_width: float, factor: float) -> float:
    """A line weight in points after 'factor', no thinner than MIN_LINE_PT."""
    return max(stroke_width * factor, min(stroke_width, MIN_LINE_PT))
