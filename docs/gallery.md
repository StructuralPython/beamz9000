# Gallery

Every diagram on this page is drawn from the scheme beside it when the
documentation is built. The schemes live in the repository's
[`examples/`](https://github.com/StructuralPython/beamz9000/tree/main/examples)
folder.

## Simply supported beam

Two uniform loads in different load cases are drawn in separate bands.

```{literalinclude} ../examples/gallery.yaml
:language: yaml
:start-at: "simple_udl:"
:end-before: "propped_cantilever:"
```

```{beam-figure} gallery.yaml simple_udl
```

## Propped cantilever

`supports` overrides the default pin and roller.

```{literalinclude} ../examples/gallery.yaml
:language: yaml
:start-at: "propped_cantilever:"
:end-before: "overhang:"
```

```{beam-figure} gallery.yaml propped_cantilever
```

## Overhang

`cantilever: right` leaves the last node free. `loc: L` is the right end.

```{literalinclude} ../examples/gallery.yaml
:language: yaml
:start-at: "overhang:"
:end-before: "floor_beam:"
```

```{beam-figure} gallery.yaml overhang
```

## Continuous floor beam with an occupancy

A pressure load that names an occupancy is drawn once, hatched, at the
occupancy's total pressure. Pressure loads are labelled with their tributary
width (at each end, if it varies, and the load tapers); the pressures are listed
in the legend.

```{literalinclude} ../examples/gallery.yaml
:language: yaml
:start-at: "floor_beam:"
:end-before: "# A core footing"
```

```{beam-figure} gallery.yaml floor_beam
```

## Core footing on soil that only pushes

A strip footing carries three columns and a lift core. Under lateral load, the
core's walls act as a couple: one flange pushes down 5000 kN, the other pulls
up 3000 kN. `foundation` puts the footing on soil, and `[null, 20 MPa/m]`
makes it compression only, so the heel under the tension flange lifts off
instead of being held down. `pressure` draws the soil pressure under the
footing, which falls to zero where the heel lets go. See
{ref}`foundations` for how the foundation is analysed.

```{literalinclude} ../examples/gallery.yaml
:language: yaml
:start-at: "# A core footing"
```

```{beam-figure} gallery.yaml core_footing
:size: 6.5 7.6
```

## Springs, depth and angled loads

```{literalinclude} ../examples/drawing_features.yaml
:language: yaml
:start-at: "B2:"
:end-before: "B3:"
```

```{beam-figure} drawing_features.yaml B2
```

```{literalinclude} ../examples/drawing_features.yaml
:language: yaml
:start-at: "B3:"
```

```{beam-figure} drawing_features.yaml B3
```

## Everything at once

The starter example uses every load type, global and span-relative locations,
an occupancy, unfactored and factored loads, and separate load combinations
for forces and deflections.

```{literalinclude} ../examples/beam_scheme.yaml
:language: yaml
```

```{beam-figure} beam_scheme.yaml B1
```
