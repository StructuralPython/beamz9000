# Customizing

## Layout

{class}`~beamz9000.diagram.layout.Layout` holds every size and style a
diagram uses. Sizes are fractions of the beam length, so a 3 m cantilever and
an 18 m continuous beam come out with the same proportions. Line weights are in
points.

```python
import beamz9000 as bz

layout = bz.Layout(
    font_family="DejaVu Serif",
    font_size=0.022,           # × beam length
    point_height=0.12,         # arrow length of the largest point load
    palette=["#222222", "#C0392B", "#2471A3"],
    legend_title="Loads",
)
bz.draw("beams.yaml", "B1.svg", layout=layout)
```

Turn the legend off with `legend=False`. Every field is listed in the
{class}`API reference <beamz9000.diagram.layout.Layout>`.

## Renderers

Pass a renderer to choose its settings:

```python
bz.draw("beams.yaml", "B1.png", renderer=bz.MatplotlibRenderer(width=8, dpi=300))
bz.draw("beams.yaml", "B1.svg", renderer=bz.SVGRenderer(width=900, embed_font=True))
```

`embed_font=True` embeds the measured font in the SVG with `@font-face`, so
every viewer draws exactly the glyphs the layout measured. Without it, a viewer
missing the font substitutes another and labels may sit slightly off.

`MatplotlibRenderer.figure()` returns a matplotlib `Figure` for further work,
and `to_bytes()` returns the encoded file without writing it.

## Fitting to a size

Reports and calc sheets have a fixed space for a figure. Give the renderer a
`height` as well as a `width` and the output is exactly that size:

```python
renderer = bz.MatplotlibRenderer(width=6.5, height=2.5)   # inches
bz.draw("beams.yaml", "B1.png", renderer=renderer)
```

`draw` then arranges the diagram to fill the box, not only scale it:

- **The load strata stretch or squeeze.** Load heights and the gaps between
  bands are scaled, within `Layout.stretch` (0.6 to 2 by default), toward the
  box's shape. Text, supports and dimensions keep their size and spacing.
- **The legend moves on top when that's better.** With
  `legend_position="auto"` (the default), the legend goes above the loads when
  that draws the beam larger than a legend on the right. On top, its keys run
  in rows that wrap at the drawing's width.

Whatever space is left is shared equally on both sides, so the drawing is
centred.

The same beam, fitted to 6.5 × 2 in (legend on the right, loads squeezed):

```{beam-figure} beam_scheme.yaml B1
:size: 6.5 2
```

and to 6.5 × 3.5 in (legend on top):

```{beam-figure} beam_scheme.yaml B1
:size: 6.5 3.5
```

Without a renderer, call `beam_diagram` with the box's `aspect` (width ÷
height). Pass the renderer's `margin` too, so the fit counts it:

```python
diagram = bz.beam_diagram("beams.yaml", aspect=6.5 / 2.5)
```

Set `legend_position="right"` or `"top"` to fix the legend's place, and
`stretch=(1, 1)` to keep the layout's proportions.

## Changing a finished diagram

{func}`~beamz9000.diagram.compose.beam_diagram` returns a
{class}`~beamz9000.graphics.elements.Group`: an immutable tree of shapes and
texts. Each part carries a `role` (`loads`, `beam`, `supports`,
`node_labels`, `dimensions`, `legend`), and each load a `key` (its load case
or occupancy). The functions in {mod}`beamz9000.graphics.elements` return new
elements, so you can change a diagram before drawing it:

```python
from beamz9000.graphics.elements import group, restyle

diagram = bz.beam_diagram("beams.yaml", beam_id="B1")
loads, beam, supports, labels, dims, legend = diagram.children

# Print-friendly: every load in black.
loads = restyle(loads, stroke_color="black", fill_color="black")
bz.draw(group(loads, beam, supports, labels, dims), "B1-mono.pdf")
```

`translate`, `rotate`, `scale`, `mirror_x` and `mirror_y` move elements, and
keep text upright and readable.

## Drawing from your own analysis

The diagram code reads a {class}`~beamz9000.spec.BeamSpec`, not the YAML
scheme: nodes, supports and loads as plain floats with the labels to draw. An
adapter from another model (an analysis program, a database) only needs to
build one:

```python
from beamz9000 import BeamSpec
from beamz9000.spec import LegendKey, SpecLoad

spec = BeamSpec(
    nodes=[0.0, 6.0],
    supports=["pin", "roller"],
    loads=[SpecLoad(kind="line", key="D", x1=0, x2=6, mag1=4.5e3, mag2=4.5e3, label1="4.5 kN/m")],
    keys=[LegendKey(name="D", kind="case")],
    span_labels=["6 m"],
    length_label="6 m",
)
bz.draw(spec, "from-spec.png")
```
