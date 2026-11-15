# ymprint block

[ymprint](https://ymprint.structuralpython.com) builds PDF reports from YAML.
beamz9000 adds a `_beam` block that draws a beam's free-body diagram straight
into the report. The diagram is vector graphics with real, searchable text,
sized to the space the report gives it.

```bash
uv add "beamz9000[ymprint]"
```

ymprint needs Python 3.14 or later.

## Use it

beamz9000 registers `_beam` as an installed block (the `ymprint.blocks`
entry point), so `ym` renders it once both are installed:

```bash
ym convert report.yml
ym live report.yml
```

ymprint 0.12 and later read blocks from installed packages, so `ym` renders
`_beam` with nothing to register. The extra requires ymprint 0.12 or later.

In the report, point the block at a scheme file:

```yaml
Beam design:
  - Beam B1:
      - _beam_b1:
          scheme: beams.yaml       # relative to the report
          beam: B1                 # which beam, if the file has several
          caption: Beam B1 loading
```

or write the beam inline, in the {doc}`scheme format <scheme>`. Quantities
work without an `_environment` key (the "structural" environment is used):

```yaml
  - Cantilever C1:
      - _beam_c1:
          beam:
            spans: [3 m]
            cantilever: right
            node_labels: auto
            loads:
              - dist: {w: 4 kN/m, case: D}
              - point: {p: 10 kN, loc: L, case: L}
          width_ratio: 0.6
```

A beam built in Python can be passed in as a variable, e.g. `beam: $b1`, where
`b1` is a {class}`~beamz9000.scheme.Beam`, {class}`~beamz9000.spec.BeamSpec` or
one-beam {class}`~beamz9000.scheme.Scheme`.

## Options

| Key | Default | Meaning |
|---|---|---|
| `scheme` | | A beamz9000 scheme file, relative to the report. Live mode re-renders when it changes. |
| `beam` | | With `scheme`, the id of the beam to draw. Without it, the beam itself. |
| `width_ratio` | `1` | Width, as a fraction of the available width. |
| `height` | | Height, e.g. `60 mm`, `2.5 in`, `180 pt` (a plain number is points). The diagram is arranged to fill width × height (see {ref}`fitting <fitting-to-a-size>`). |
| `max_height_ratio` | `0.6` | Without `height`, the diagram takes its natural height, up to this fraction of the available height. Beyond it, the diagram is fitted to that height instead. |
| `font_size` | `9` | Text size, in points. Supports, arrowheads and legend swatches scale with it. |
| `legend` | `auto` | `auto`, `right`, `top` or `none`. |
| `caption` | | A caption under the diagram, in the report's image caption style. |
| `environment` | `structural` | The forallpeople environment for an inline beam. |
| `layout` | | Any other {class}`~beamz9000.diagram.layout.Layout` setting, e.g. `{palette: ["#000", "#c00"]}`. |

Mistakes are reported as ymprint block errors that name the block, e.g.
`Block '_beam_c1': load 1 (point) at 9 m is off the beam (length 3 m)`.

## In your own application

Your own ymprint applications pick up `_beam` as an installed block too,
unless they're created with `plugin_blocks=False`. To add it explicitly, or
under another code, use {func}`~beamz9000.ymprint.register`:

```python
from ymprint import Ymprint
from beamz9000.ymprint import register

app = Ymprint(name="calcsheet")
register(app)              # as _beam; register(app, "_fbd") for another code
cli = app.cli()
```

## Outside ymprint

The block draws with {class}`~beamz9000.render.reportlab.ReportLabRenderer`,
which works in any ReportLab document:

```python
from beamz9000.render.reportlab import ReportLabRenderer

renderer = ReportLabRenderer(width=468, height=180)          # points
layout = bz.Layout(font_size_pt=8)
diagram = bz.beam_diagram("beams.yaml", layout, aspect=renderer.aspect,
                          margin=renderer.margin, width=renderer.width_pt)
story.append(renderer.flowable(diagram))                     # a platypus Flowable
renderer.save(diagram, "B1.pdf")                             # or a one-page PDF
```

Install it with `uv add "beamz9000[reportlab]"`.
