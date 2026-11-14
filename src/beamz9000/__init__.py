"""
beamz9000: beam free-body diagrams from a simple YAML scheme.

The pipeline is: scheme YAML -> `scheme.Beam` (pydantic, validated) ->
`spec.BeamSpec` (engine-neutral floats) -> shapely-based graphics elements ->
a renderer (matplotlib, SVG).
"""

__version__ = "0.1.0"
