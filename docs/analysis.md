# Analysis

List anything under `results` and beamz9000 analyses the beam before drawing
it. The diagram then shows a diagram below the dimensions for each result you
asked for and, if you list `reactions`, each support's reactions under it.
Without load combinations, every load case is drawn in its own colour. With
them, the results are envelopes over the combinations.

## Install an engine

The analysis runs on [pycba](https://github.com/ccaprani/pycba) through
[pycba-tools](https://github.com/StructuralPython/pycba-tools) by default, or
on [PyniteFEA](https://github.com/JWock82/Pynite) through
[pynite-tools](https://github.com/StructuralPython/pynite-tools):

```bash
uv add "beamz9000[pycba]"    # pycba-tools, the default engine
uv add "beamz9000[pynite]"   # pynite-tools
```

Without an engine, a beam with `results` is drawn without them, with a
warning. pycba is licensed under the AGPL-3.0; PyniteFEA under the MIT
licence.

## Ask for results

```yaml
results: [forces, deflections, reactions]
```

| Name | Draws |
|---|---|
| `reactions` | each support's reactions, under it |
| `forces` | shear and moment |
| `shear` | shear |
| `moment` | moment |
| `deflection`, `deflections` | deflection |
| `rotation`, `rotations` | rotation |

The mapping form also picks the engine:

```yaml
results:
  diagrams: [forces, rotations, reactions]
  engine: pynite      # pycba (the default) | pynite | auto
  combos: [ULS1, ULS2]   # optional: only these load combinations
```

pycba is the default. `auto` uses pycba-tools when it is installed, and
pynite-tools otherwise. Both engines give the same results.

## What is analysed

- Each load case is analysed on its own. An occupancy contributes one load per
  case in it. Every case gets a colour in the legend.
- Loads without a `case` are taken as already factored. They form one unnamed
  case, drawn in black with no legend entry. With load combinations they are
  left out, as they belong to no combination.
- Deflection and rotation need the beam's stiffness, `e` and `i` or `ei`.
  Without it they are left out, with a warning, and the forces are found with
  EI = 1, which is exact for a prismatic beam on rigid supports.
- A `spring` or `rotational_spring` needs a stiffness, and a beam on springs
  needs its EI.
- Angled point loads add a horizontal reaction at the first pin, fixed support
  or rotational spring. Rollers and vertical springs slide.

(load-combinations)=
## Load combinations

With `load_combos`, results are factored envelopes: the largest and smallest
value at each point over the combinations, drawn in black as a max curve and a
min curve, each filled to the axis.

```yaml
load_combos:              # a plain list applies to every result
  - ULS1: {D: 1.4}
  - ULS2: {D: 1.25, L: 1.5}
```

```yaml
load_combos:              # or one set per group of results
  forces:                 # reactions, shear and moment
    - ULS1: {D: 1.4}
    - ULS2: {D: 1.25, L: 1.5}
  deflections:            # deflection and rotation
    - SLS: {D: 1.0, L: 1.0}
```

- A result whose group has no combinations shows each load case instead. For
  example, with only `forces:` combinations, deflections are drawn per case.
- Reactions list each load case's components, then the factored `max` and
  `min` of each component over the `forces` combinations.
- A factor on a case that no load uses is ignored, so a standard set of
  combinations can be shared between beams. A combination may not share a
  load case's name.

```{literalinclude} ../examples/analysis.yaml
:language: yaml
:start-at: "factored_floor_beam:"
```

```{beam-figure} analysis.yaml factored_floor_beam
:size: 6.5 5.6
```

## Reading the diagram

```{beam-figure} analysis.yaml floor_beam
:size: 6.5 5.2
```

- **Reactions** read `↑ 9.93 kN`: an arrow for the direction (`↑` `↓` for
  vertical, `→` `←` for horizontal, `↺` `↻` for moment) and the magnitude, one
  line per load case, then `max` and `min` lines with load combinations. Where
  supports are close together, a support's reactions move toward open space or
  go one per line.
- **Shear** is positive where the left-hand part is pushed up.
- **Moment** is drawn on the tension side: positive (sagging) moment hangs
  below the axis, and hogging moment over a support rises above it. Set
  `Layout(moment_on_tension_side=False)` to draw sagging moment upward.
- **Deflection** is drawn as the beam deflects, and **rotation** is positive
  counter-clockwise.
- Each case's peaks are marked with dots and listed to the right, as
  `max / min`. An envelope lists its `max` and `min`.

Results are given in the units the scheme uses: a beam loaded in kN gets
reactions in kN, moments in kN·m and deflections in mm.

## Using the analysis directly

{func}`beamz9000.analysis.analyze` returns the reactions and the curves as
plain floats in SI base units:

```python
import beamz9000 as bz
from beamz9000 import analysis

beam = bz.load_scheme("analysis.yaml")["floor_beam"]
result = analysis.analyze(beam, ["moment", "deflection"])

result.reaction(1, "L")                  # Reaction(node=1, case='L', fy=47033.6, ...)
max(result.curve("moment", "D").y)       # sagging moment, N·m

factored = analysis.analyze(bz.load_scheme("analysis.yaml")["factored_floor_beam"], ["moment"])
factored.envelope("moment")              # Envelope(quantity='moment', x=..., max=..., min=...)
factored.reaction_envelopes()[0].fy      # (max, min) at node 0, N
```

The model is built through the tools packages' shared interface:
{func}`~beamz9000.analysis.model_dict` writes it in the engine's JSON schema
(save it with `json.dump` and open it in pycba-tools or pynite-tools), and
{func}`~beamz9000.analysis.build_model` loads it with the package's
`load_dict` and analyses it, returning a model with each load case as a load
combination of the same name, beside the scheme's own combinations.

## Examples

```{literalinclude} ../examples/analysis.yaml
:language: yaml
:start-at: "cantilever:"
:end-before: "on_springs:"
```

```{beam-figure} analysis.yaml cantilever
```

```{literalinclude} ../examples/analysis.yaml
:language: yaml
:start-at: "on_springs:"
:end-before: "factored_floor_beam:"
```

```{beam-figure} analysis.yaml on_springs
```
