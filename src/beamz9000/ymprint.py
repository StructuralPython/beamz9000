"""
A `_beam` block for ymprint documents (https://ymprint.structuralpython.com).

The block draws a beam's free-body diagram as vector graphics with real,
searchable text, sized to the space the document gives it::

    Beam B1:
      - _beam_b1:
          scheme: beams.yaml     # a beamz9000 scheme file, relative to the document
          beam: B1               # which beam, if the file has several
          height: 60 mm          # optional; the diagram fills width x height
          caption: Beam B1 loading

or with the beam written inline (quantities need no `_environment`; the
"structural" environment is used)::

      - _beam:
          beam:
            spans: [4.5 m, 2.5 m]
            cantilever: right
            loads:
              - dist: {w: 2.5 kN/m, case: D}

beamz9000 provides the block through the `ymprint.blocks` entry point, so
`ym convert report.yml` renders it (ymprint 0.12 and later). `register(app)`
adds it to an application explicitly, for one built with `plugin_blocks=False`
or under another code.

Requires the `ymprint` extra: `uv add "beamz9000[ymprint]"`.
"""

from __future__ import annotations

import pathlib
import re
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from reportlab.platypus import Paragraph, Table, TableStyle
from ymprint import Ymprint
from ymprint.blocks import blockstyles, content_box
from ymprint.errors import BlockError

from beamz9000.diagram import Layout, beam_diagram
from beamz9000.diagram.compose import as_spec
from beamz9000.render.reportlab import ReportLabRenderer
from beamz9000.scheme import Beam, Scheme, load_scheme, parse_scheme
from beamz9000.spec import BeamSpec

BLOCK_CODE = "_beam"

# Points per unit, for lengths written with units in a block.
_POINTS = {"pt": 1.0, "in": 72.0, "mm": 72 / 25.4, "cm": 72 / 2.54}
_LENGTH = re.compile(r"^\s*([0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s*(pt|in|mm|cm)?\s*$")


def to_points(value: Union[int, float, str]) -> float:
    """Returns a length in points: a plain number is points, or "60 mm", "2.5 in", "180 pt"."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    match = _LENGTH.match(str(value))
    if not match:
        raise ValueError(f"{value!r} is not a length; write e.g. 60 mm, 2.5 in, 180 pt, or a number of points")
    return float(match.group(1)) * _POINTS[match.group(2) or "pt"]


class BeamBlock(BaseModel):
    """The data under a `_beam` key."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    scheme: Optional[str] = Field(None, description="A scheme file, relative to the document.")
    beam: Any = Field(
        None,
        description="With `scheme`, the id of the beam to draw. Without it, the beam itself: a "
        "mapping in the scheme format, or a Beam, BeamSpec or Scheme passed in as a $variable.",
    )
    environment: str = Field("structural", description="The forallpeople environment for an inline beam.")
    width_ratio: float = Field(1.0, gt=0, le=1, description="Width, as a fraction of the space available.")
    height: Optional[float] = Field(
        None, description="Height, e.g. 60 mm. Without it, the height follows the diagram's shape.",
    )
    max_height_ratio: float = Field(
        0.6, gt=0, le=1,
        description="Without a height: the most of the available height the diagram may take "
        "before it is fitted to that height instead.",
    )
    font_size: float = Field(9.0, gt=0, description="Text size, in points.")
    legend: Optional[Literal["auto", "right", "top", "none"]] = Field(
        None, description="Legend placement. Without it, the scheme's `display.legend`, else auto.",
    )
    caption: Optional[str] = None
    layout: dict = Field(default_factory=dict, description="Any other diagram Layout settings.")

    @field_validator("height", mode="before")
    @classmethod
    def _height(cls, value):
        return None if value is None else to_points(value)


def beam_block(block_key: str, block_value: Any, context: dict) -> list:
    """
    The `_beam` block converter: returns the beam's diagram as a ReportLab
    flowable (with its caption, if any), sized to the document's content box.
    """
    try:
        block = BeamBlock.model_validate(block_value or {})
        spec = _spec(block, block_key, context)
        legend = {}
        if block.legend == "none":
            legend = {"legend": False}
        elif block.legend is not None:
            legend = {"legend_position": block.legend}
        layout = Layout(**{**block.layout, "font_size_pt": block.font_size, **legend})
    except (ValidationError, ValueError, TypeError) as err:
        raise BlockError(block_key, f"Block {block_key!r}: {_message(err)}") from err

    box = content_box(context)
    width = box["width"] * block.width_ratio
    height = block.height
    if height is not None:
        height = min(height, box["height"])
    renderer = ReportLabRenderer(width=width, height=height)
    diagram = _diagram(spec, layout, renderer)
    if height is None:
        # Natural height, unless that takes too much of the page.
        limit = box["height"] * block.max_height_ratio
        if renderer.size(diagram)[1] > limit:
            renderer = ReportLabRenderer(width=width, height=limit)
            diagram = _diagram(spec, layout, renderer)

    rows = [[renderer.flowable(diagram)]]
    if block.caption:
        style = blockstyles.get_text_styles(blockstyles.block_scale(context)).get("image_caption")
        rows.append([Paragraph(block.caption, style=style)])
    table = Table(rows, colWidths=[width])
    table.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return [table]


def register(app: Ymprint, code: str = BLOCK_CODE, *, override: bool = False) -> None:
    """Adds the `_beam` block (or 'code') to a ymprint application."""
    app.register_block(code, beam_block, override=override)


def _diagram(spec: BeamSpec, layout: Layout, renderer: ReportLabRenderer):
    return beam_diagram(spec, layout, aspect=renderer.aspect, margin=renderer.margin, width=renderer.width_pt)


def _spec(block: BeamBlock, block_key: str, context: dict) -> BeamSpec:
    beam = block.beam
    if block.scheme is not None:
        path = pathlib.Path(context.get("base_dir", ".")) / block.scheme
        if "data" in context:
            # Recorded even when missing, so live mode re-renders once it exists.
            context["data"].record_file(path)
        if not path.exists():
            raise ValueError(f"the scheme file was not found: {path}")
        if beam is not None and not isinstance(beam, str):
            raise ValueError("with `scheme`, `beam` is the id of a beam in it")
        return as_spec(load_scheme(path), beam)
    if isinstance(beam, (Beam, BeamSpec, Scheme)):
        return as_spec(beam)
    if isinstance(beam, dict):
        data = dict(beam)
        name = data.pop("id", None) or _block_id(block_key) or "beam"
        return as_spec(parse_scheme({"_environment": block.environment, name: data}), name)
    raise ValueError("give a `scheme` file, or the `beam` itself")


def _block_id(block_key: str) -> Optional[str]:
    from ymprint import parse_block_key

    parsed = parse_block_key(block_key)
    return parsed[1] if parsed else None


def _message(err: Exception) -> str:
    if isinstance(err, ValidationError):
        return "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" if e["loc"] else e["msg"]
            for e in err.errors()
        )
    return str(err)


app = Ymprint(name="beamz")
register(app)

if __name__ == "__main__":
    app.cli()()
