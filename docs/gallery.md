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
```

```{beam-figure} gallery.yaml floor_beam
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
