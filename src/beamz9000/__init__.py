"""
beamz9000: beam free-body diagrams from a simple YAML scheme.

The pipeline is: scheme YAML -> `scheme.Beam` (pydantic, validated) ->
`spec.BeamSpec` (engine-neutral floats) -> shapely-based graphics elements ->
a renderer (matplotlib, SVG).

    import beamz9000 as bz
    bz.draw("examples/beam_scheme.yaml", "B1.png")
"""

from __future__ import annotations

import pathlib
from typing import Optional, Union

from beamz9000.diagram import Layout, as_spec, beam_diagram
from beamz9000.graphics.elements import Group, Shape, Text
from beamz9000.render import MatplotlibRenderer, SVGRenderer
from beamz9000.scheme import Beam, Scheme, load_scheme, parse_scheme
from beamz9000.spec import BeamSpec, from_scheme

__version__ = "0.1.0"


def draw(obj, path: Union[str, pathlib.Path], layout: Optional[Layout] = None,
         beam_id: Optional[str] = None, renderer=None) -> pathlib.Path:
    """
    Draws the free-body diagram of 'obj' (a scheme file path, Scheme, Beam,
    BeamSpec, or an already-built diagram Group) to 'path'. The suffix picks
    the format: .svg uses the native SVGRenderer, anything else (png, pdf,
    ...) the MatplotlibRenderer, unless 'renderer' is given.
    """
    path = pathlib.Path(path)
    diagram = obj if isinstance(obj, Group) else beam_diagram(obj, layout, beam_id)
    if renderer is None:
        renderer = SVGRenderer() if path.suffix.lower() == ".svg" else MatplotlibRenderer()
    return renderer.save(diagram, path)


__all__ = [
    "Beam", "BeamSpec", "Group", "Layout", "MatplotlibRenderer", "SVGRenderer", "Scheme",
    "Shape", "Text", "as_spec", "beam_diagram", "draw", "from_scheme", "load_scheme", "parse_scheme",
]
