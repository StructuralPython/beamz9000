# How it works

```text
scheme YAML ─► scheme.Beam ─► spec.BeamSpec ─► graphics elements ─► renderer
              (pydantic,      (engine-neutral   (shapely geometry    (matplotlib:
               validated,      SI floats,        + style, Text,       png/pdf;
               locations       legend keys,      Group)               native SVG)
               resolved)       labels)
```

## Scheme

{mod}`beamz9000.scheme` parses the YAML into pydantic models. It accepts the
loose forms people write (`{point: {...}}` or `{type: point, ...}`, `p` or
`mag`, a list or a mapping of occupancies) and normalizes them. Validation
resolves every location to a distance from the left end, checks dimensions, and
names the load at fault when something is wrong.

When the file names a forallpeople environment, quantity strings are parsed to
{class}`~beamz9000.units.Quantity` objects. A `Quantity` is a forallpeople
`Physical` that also remembers the text it was written as, so `12 kN/mm` is
labelled "12 kN/mm", not "12 MN/m".

## BeamSpec

{func}`~beamz9000.spec.from_scheme` reduces a beam to what a drawing needs:
node positions, supports, and loads as SI floats, each with its legend key and
label text. The drawing code never sees the scheme, so any other source of
beams can draw through the same code by building a `BeamSpec`.

## Graphics elements

Shapely geometry has no style. {mod}`beamz9000.graphics.elements` wraps it:

- {class}`~beamz9000.graphics.elements.Shape`: a geometry with
  {class}`~beamz9000.graphics.elements.Stroke` (colour, opacity, width, line
  type) and {class}`~beamz9000.graphics.elements.Fill` (colour, opacity,
  hatch).
- {class}`~beamz9000.graphics.elements.Text`: a label with an anchor,
  alignment, rotation and {class}`~beamz9000.graphics.elements.Font`.
- {class}`~beamz9000.graphics.elements.Group`: an ordered tree of elements.

Elements are frozen; transforms return new ones. A whole diagram serializes to
JSON (geometry as GeoJSON) and reads back equal.

Glyphs ({mod}`beamz9000.graphics.glyphs`) are small pure functions that build
geometry at the origin: a pin, a roller, a spring coil, an arrow, a moment arc,
a load trapezoid. Their proportions follow
[fbd_plotting](https://github.com/StructuralPython/fbd_plotting). The diagram
functions in {mod}`beamz9000.diagram.compose` orient, place and style them.

## Text

Text is never turned into outlines. Labels are drawn as native text in every
output, so they can be searched and selected. To lay out labels without
overlaps, {mod}`beamz9000.graphics.text` measures each one with
[libraqm](https://github.com/HOST-Oman/libraqm) shaping (bundled with
matplotlib), including kerning, using the same font file the renderers draw
with.

## Diagram strata

{func}`~beamz9000.diagram.compose.beam_diagram` stacks, from top to bottom:

1. **Loads**, in one band per load case, occupancy, or "Factored". Overlapping
   loads in a band are packed into rows.
2. **The beam**, as a line, or as a rectangle to scale when it has a depth.
3. **Supports**, with spring stiffnesses beside them, then node labels.
4. **Dimensions**: each span, then the overall length.

The legend sits to the right.

## Renderers

Renderers walk the flattened element tree in z-order:

- {class}`~beamz9000.render.matplotlib.MatplotlibRenderer` draws shapes as
  `PathPatch`es and text as `Text` artists (TrueType fonts embedded in PDF).
- {class}`~beamz9000.render.svg.SVGRenderer` writes `<path>`, `<text>` and
  `<pattern>` elements directly.
