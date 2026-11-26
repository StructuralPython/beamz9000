---
og:description: Beam free-body diagrams from a simple YAML scheme.
---

```{image} _static/logo.svg
:alt: beamz9000 logo
:width: 120px
:class: front-logo
```

# beamz9000

**Beam free-body diagrams from a simple YAML scheme.** Write down the spans,
supports and loads of a 2D beam the way you would sketch them, and get a clean,
consistent diagram as PNG, PDF or SVG.

```{beam-figure} drawing_features.yaml B2
:no-downloads:
A three-span beam with a rotational spring, a vertical spring, angled point
loads and a drawn depth, from `examples/drawing_features.yaml`.
```

```{literalinclude} ../examples/drawing_features.yaml
:language: yaml
:start-at: "B2:"
:end-before: "B3:"
:prepend: "_environment: structural\n"
```

```python
import beamz9000 as bz

bz.draw("drawing_features.yaml", "B2.svg", beam_id="B2")
```

## What you get

- **One scheme format.** Spans, cantilevers, supports (including springs),
  point, distributed, pressure and moment loads, occupancies, load
  combinations. Locations can be global (`loc: -500 mm`, `loc: L`) or relative
  to a span (`span_loc: [1, 1250 mm]`).
- **Units if you want them.** Write plain numbers, or quantities such as
  `12 kN/mm` through [forallpeople](https://github.com/connorferster/forallpeople).
  Labels show the units you wrote.
- **Helpful validation.** Errors name the load and the problem: `load 3
  (dist): it must end after it starts`.
- **Analysis built in.** List `results: [forces, deflections, reactions]` and
  the beam is analysed with pycba or PyniteFEA: shear, moment, deflection and
  rotation diagrams below, and reactions under every support. Per load case,
  or as factored envelopes over your load combinations.
- **Beams on soil.** `foundation: {ks: [null, 20 MPa/m], width: 2500 mm}` puts
  a footing on an elastic foundation, linear or compression only, and
  `results: [pressure]` draws the soil pressure under it. Where soil would
  have to pull, the footing lifts off instead.
- **Diagrams that read the same every time.** Loads are drawn in bands per load
  case or occupancy, above the beam, then the supports and the dimensions, with
  a colour-blind-safe legend.
- **Searchable text.** Labels stay text in every output, shaped with libraqm so
  the space reserved for each label is the space it takes.
- **Geometry you can reuse.** Every diagram is built from
  [shapely](https://shapely.readthedocs.io) geometry with style attached. Draw it
  with the built-in renderers, or walk the elements and draw them anywhere.

```{toctree}
:hidden:
:caption: Guide

getting-started
scheme
gallery
analysis
customizing
ymprint
architecture
```

```{toctree}
:hidden:
:caption: Reference

api/index
```
