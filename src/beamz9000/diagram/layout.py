"""
Layout settings for beam diagrams.

Sizes are fractions of the beam length, so a 3 m cantilever and an 18 m
continuous beam come out with the same proportions whatever the units. Stroke
widths are in points, like every renderer's line weights.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Okabe-Ito: a colour-blind-safe qualitative palette.
OKABE_ITO = [
    "#0072B2",  # blue
    "#D55E00",  # vermillion
    "#009E73",  # bluish green
    "#CC79A7",  # reddish purple
    "#E69F00",  # orange
    "#56B4E9",  # sky blue
    "#F0E442",  # yellow
    "#000000",  # black
]


# The proportions a fit stretches to change a diagram's aspect ratio: the load
# strata and result diagrams only, so supports, dimensions and text keep their
# spacing.
VERTICAL_FIELDS = ("point_height", "line_height", "beam_clearance", "band_gap", "row_gap", "result_height")

# Symbols that are sized like text: when text is sized in points, they scale
# with it, so a support or a legend swatch keeps its size next to a label.
SYMBOL_FIELDS = ("glyph_width", "head_length", "head_width", "moment_radius", "swatch_size", "tick_size")


class Layout(BaseModel):
    """Proportions and styles of a beam diagram. All lengths are × beam length."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Text
    font_family: str = "DejaVu Sans"
    font_size: float = Field(0.02, description="Text height, × beam length.")
    font_size_pt: Optional[float] = Field(
        None, gt=0,
        description="Text height in points. Used instead of font_size when the output "
        "width is known (draw(), or beam_diagram(width=...)), so text is the same size "
        "whatever the beam's length or the box's shape.",
    )
    label_gap: float = Field(0.25, description="Gap between a glyph and its label, in em.")

    # Beam and supports
    glyph_width: float = 0.048
    beam_stroke_width: float = Field(4.0, description="Beam line weight when it has no depth.")
    beam_fill: str = "#f2f2f2"
    beam_outline_width: float = Field(1.5, description="Beam outline weight when it has a depth.")
    support_fill: str = "#d9d9d9"
    ink: str = "black"
    stroke_width: float = 1.0

    # Loads
    point_height: float = Field(0.09, description="Arrow length of the largest point load.")
    line_height: float = Field(0.09, description="Region height of the largest line load.")
    min_fraction: float = Field(0.2, description="Smallest drawn size, as a fraction of the largest.")
    moment_radius: float = 0.028
    head_length: float = 0.014
    head_width: float = 0.01
    arrow_spacing: float = 0.05
    load_fill_opacity: float = 0.3
    load_stroke_width: float = 1.2
    area_load_hatch: str = "//"
    beam_clearance: float = Field(0.025, description="Gap between the beam and the first band.")
    band_gap: float = Field(0.03, description="Gap between bands.")
    row_gap: float = Field(0.015, description="Gap between rows within a band.")
    item_gap: float = Field(0.01, description="Smallest horizontal gap between items in a row.")
    palette: list[str] = Field(default_factory=lambda: list(OKABE_ITO))

    # Dimensions
    dimension_gap: float = Field(0.04, description="Gap below the supports to the first dimension line.")
    dimension_spacing: float = Field(0.08, description="Distance between chained and overall lines.")
    tick_size: float = 0.012
    dimension_stroke_width: float = 0.8

    # Analysis results
    reactions: bool = Field(True, description="Draw each support's reactions when the beam was analysed.")
    reaction_line: float = Field(1.25, description="Line pitch of the reactions under a support, in em.")
    result_height: float = Field(0.1, description="Height of the largest value in a result diagram.")
    result_gap: float = Field(0.06, description="Gap above each result diagram.")
    result_fill_opacity: float = 0.12
    result_stroke_width: float = 1.2
    result_axis_color: str = "#8c8c8c"
    moment_on_tension_side: bool = Field(
        True, description="Draw positive (sagging) moment below the axis, on the tension side.",
    )

    # Legend
    legend: bool = True
    legend_position: Literal["auto", "right", "top"] = Field(
        "auto",
        description="Where the legend goes. 'auto' puts it on the right, unless the diagram "
        "is fitted to a target aspect ratio and it fits better on top.",
    )
    legend_gap: float = Field(0.05, description="Gap between the drawing and a legend on the right.")
    legend_top_gap: float = Field(0.03, description="Gap between the drawing and a legend on top.")
    legend_item_gap: float = Field(1.5, description="Gap between legend items in a row on top, in em.")
    swatch_size: float = 0.022
    legend_row: float = Field(1.8, description="Legend row pitch, in em.")
    legend_title: str | None = Field(None, description="Title; chosen from the keys if None.")

    # Fitting to a target aspect ratio
    stretch: tuple[float, float] = Field(
        (0.6, 2.0),
        description="Range of factors a fit may apply to the load strata (load heights "
        "and the gaps between bands and rows) to match a target aspect ratio. "
        "(1, 1) turns stretching off.",
    )

    @model_validator(mode="after")
    def _check_stretch(self):
        lo, hi = self.stretch
        if not 0 < lo <= 1 <= hi:
            raise ValueError("`stretch` must be (low, high) with 0 < low <= 1 <= high")
        return self

    def stretched(self, factor: float) -> "Layout":
        """Returns this layout with its vertical proportions × 'factor'. Text is unchanged."""
        if factor == 1:
            return self
        return self.model_copy(update={k: getattr(self, k) * factor for k in VERTICAL_FIELDS})

    def text_scaled(self, factor: float) -> "Layout":
        """Returns this layout with its text and symbols × 'factor'."""
        update = {k: getattr(self, k) * factor for k in ("font_size", *SYMBOL_FIELDS)}
        return self.model_copy(update=update)

    def color(self, index: int) -> str:
        return self.palette[index % len(self.palette)]
