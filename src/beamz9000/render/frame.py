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
