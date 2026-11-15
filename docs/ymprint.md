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
| `legend` | | `auto`, `right`, `top` or `none`. Without it, the scheme's `display: {legend: ...}`, else `auto`. |
| `caption` | | A caption under the diagram, in the report's image caption style. |
| `environment` | `structural` | The forallpeople environment for an inline beam. |
| `namespace` | the beam's id | The variable the analysis results go in (see {ref}`ymprint-results`). |
| `layout` | | Any other {class}`~beamz9000.diagram.layout.Layout` setting, e.g. `{palette: ["#000", "#c00"]}`. |

Mistakes are reported as ymprint block errors that name the block, e.g.
`Block '_beam_c1': load 1 (point) at 9 m is off the beam (length 3 m)`.

(ymprint-results)=
## Results in the document

When the scheme asks for `results`, the block analyses the beam once, draws
the results, and puts them in the document's variables under the beam's id
(for an inline beam, its `id`, else the block's id, e.g. `c1` for `_beam_c1`),
or under `namespace`. The rest of the document can then use them:

```yaml
Beam B1:
  - _beam:
      scheme: analysis.yaml
      beam: factored_floor_beam
      namespace: fb
  - "The largest reaction at B is {{ fb.reactions.B.max.Fy | round(1) }} {{ fb.units.force }}."
```

The values are in the units the scheme uses (`units` says which). For
`factored_floor_beam` the variable holds:

```python
{
  "engine": "pycba",
  "units": {"force": "kN", "moment": "kN·m", "deflection": "mm", "rotation": "rad", "x": "m"},
  "cases": ["D", "L"],
  "combos": {"forces": ["ULS1", "ULS2", "ULS3"], "deflections": ["SLS"]},
  "reactions": {
    "A": {"D": {"Fy": 9.6, "Mz": 0.0, "Fx": 0.0}, "L": {...}, "ULS1": {...}, ...,
          "max": {"Fy": 26.9, ...}, "min": {...}},
    ...
  },
  "shear": {"ULS1": {"max": ..., "x_max": ..., "min": ..., "x_min": ...}, ..., "envelope": {...}},
  "moment": {...},
  "deflection": {"SLS": {...}, "envelope": {...}},
  "model": <the analysed pycba-tools CBAModel or Pynite FEModel3D>,
}
```

- Supports are keyed by their node label, or `N0`, `N1`, ... without one.
  Loads without a `case` are under `uncased`.
- Each result asked for lists each load case, or, when its group has load
  combinations, each combination and their `envelope`, as `max` and `min`
  with where along the beam they occur (`x_max`, `x_min`). Moment is positive
  sagging. Reactions list each case, each force combination, then their `max`
  and `min`.
- `units` is null for a scheme in plain numbers.

### Exporting the results and the model

Everything but `model` is plain numbers, strings, lists and dicts, so the
variable can be exported as it is:

```yaml
_export:
  fb: $fb
```

`model` is exported too: beamz9000 registers a ymprint export serializer that
writes it with its tools package's `dump_dict`. The JSON is the model's input
data with a `metadata` block naming the library and the versions that wrote it:

```json
"metadata": {"library": "pycba", "library_version": "1.0.2",
             "generator": "pycba-tools", "generator_version": "0.2.0"}
```

A document that reads the export back through `_data` gets a model again,
built with the tools package's `load_dict` (call `analyze()` on it for
results). To export only the model, give it its own variable in a `_py` block
(`source: fb_model = fb["model"]`) and export `$fb_model`.

The results come from {func}`beamz9000.results.results_dict`, which can be
used outside ymprint with {func}`beamz9000.analysis.analyze`.

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
