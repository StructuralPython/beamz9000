# beamz9000

Beam free-body diagrams from a simple YAML scheme, drawn through shapely geometry.

```python
import beamz9000 as bz

bz.draw("examples/beam_scheme.yaml", "B1.png")   # or .pdf, .svg
```

## How it works

```
scheme YAML ──► scheme.Beam ──► spec.BeamSpec ──► graphics elements ──► renderer
              (pydantic,       (engine-neutral    (shapely geometry     (matplotlib:
               validated,       SI floats, legend   + style mixins,      png/pdf/svg;
               locations        keys, labels)       Text, Group)         native SVG)
               resolved)
```

- **shapely is the intermediate type.** Supports, arrows, load regions and
  dimension ticks are `Polygon`s and `LineString`s built by small pure
  functions in `graphics/glyphs.py` (the decomposition and proportions follow
  fbd_plotting). Each glyph is drawn at the origin, then oriented and placed.
- **Style lives next to the geometry**, never inside a backend. `Shape`,
  `Text` and `Group` (`graphics/elements.py`) are frozen pydantic models built
  from `Stroke` (colour, opacity, width, line type), `Fill` (colour, opacity,
  hatch) and `Font` mixins, plus z-order, legend key and role. `translate`,
  `rotate`, `scale`, `mirror_x/y` and `restyle` return new elements. A whole
  diagram serializes to JSON and reads back equal.
- **Text stays text.** Labels are drawn as native, searchable text (matplotlib
  Text artists with TrueType embedded in PDF, `<text>` in SVG). Layout
  measures each label with libraqm shaping (bundled with matplotlib ≥ 3.11),
  so the space it reserves is the space the label is drawn in.
- **Strata, top to bottom:** load bands (one per load case, occupancy, or
  "Factored", with overlapping loads packed into rows), the beam, supports,
  dimensions, and a legend to the right. Sizes are fractions of the beam length
  (`diagram.Layout`), and the palette is colour-blind safe (Okabe-Ito).

## The scheme format

A scheme file maps beam ids to beams. Write plain numbers in any consistent
unit system, or name a [forallpeople](https://github.com/connorferster/forallpeople)
environment and write quantities:

```yaml
_environment: structural   # optional; enables "4500 mm", "2.5 kN/m", ...

B1:
  spans: [4500 mm, 2500 mm]
  cantilever: right          # left | right | both
  e: 200 GPa                 # optional; or `ei:`
  i: 300e6 mm**4
  supports: [pin, roller, free]   # optional override (see below)
  loads:
    - point:    {p: 15 kN, span_loc: [1, 1250 mm], case: L}
    - point:    {mag: 10 kN, loc: -500 mm}             # no case: already factored
    - dist:     {mag: 2.5 kN/m, case: D}               # no locations: whole beam
    - dist:     {mag1: 1 kN/m, mag2: 4 kN/m, x1: 1000 mm, span_loc2: [0, S], case: L}
    - pressure: {mag: residential, trib_width1: 3 m, trib_width2: 1.5 m, span_loc1: [1, 0 mm], loc2: L}
    - moment:   {mag: 5 kN*m, loc: 0 mm}
  occupancies:
    - residential: {D: 1.5 kPa, L: 1.9 kPa}
  load_combos:
    - ULS1: {name: D, factor: 1.4}
    - ULS2: {D: 1.25, L: 1.5}
  results:
    diagrams: [moment, shear, deflection]
```

### Locations

| Written | Means |
|---|---|
| `loc: 2000` (alias `x`) | 2000 from the left end |
| `loc: -500` | 500 back from the right end (L − 500) |
| `loc: L` | the right end |
| `span_loc: [1, 1250]` | 1250 into span 1 (spans count from 0) |
| `span_loc: [1, -250]` | 250 back from the end of span 1 |
| `span_loc: [0, S]` | the end of span 0 |
| `span_loc: 0` | the end of span 0 (a bare index) |

A `dist` or `pressure` load takes `loc1`/`x1`/`span_loc1` and
`loc2`/`x2`/`span_loc2`. Leaving out the start means the left end, and leaving
out the end means the right end.

### Loads

| Type | Magnitude | Notes |
|---|---|---|
| `point` | `mag` (aliases `magnitude`, `p`) | Positive acts downward. |
| `moment` | `mag` (aliases `magnitude`, `m`) | Positive is counter-clockwise. |
| `dist` | `mag` (aliases `magnitude`, `w`) for a UDL, or `mag1` → `mag2` | Linear between the two. |
| `pressure` | `mag` (aliases `magnitude`, `q`, `occupancy`) × `trib_width1` → `trib_width2` | `trib_width`/`trib` gives a uniform width. `mag` may name an occupancy: the load then stands for one pressure per case in it, or only `case` if given. |

Every load takes an optional `case` (with no case, the load is already factored)
and an optional `label` that replaces the drawn magnitude. Loads may also be
written flat, as `{type: point, p: 15, loc: 2000}`.

### Supports

Without `supports`, the first supported node is pinned and the rest are
rollers, with cantilevered ends left free. A single span with one cantilevered
end is fixed at the other end. `supports` overrides this, either with one type
per node (`pin`, `roller`, `fixed`, `free`) or as `{node index: type}` for just
the nodes that differ. If `cantilever` is also given, `supports` must leave
that end free.

### Occupancies, combinations, results

- `occupancies` and `load_combos` accept a list of `- name: {...}` items or a
  plain mapping.
- A combination is `{name: D, factor: 1.4}`, a list of those, or
  `{D: 1.25, L: 1.5}`.
- `results.diagrams` lists any of `moment`, `shear`, `deflection`, `rotation`.
  Deflection and rotation need `e` and `i` (or `ei`). Without them they are
  skipped, with a warning.

### Validation

Errors name the load and the problem, for example `load 3 (dist): it must end
after it starts`. Other checks:

- every load lands on the beam
- span offsets stay inside their span
- quantities have the right dimensions
- a beam doesn't mix quantities with bare numbers
- named occupancies exist
- supports agree with `cantilever`

## Development

```
uv sync
uv run pytest
```
