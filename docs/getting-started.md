# Get started

## Install

beamz9000 needs Python 3.12 or later.

::::{tab-set}
:::{tab-item} uv
```bash
uv add beamz9000
```
:::
:::{tab-item} pip
```bash
pip install beamz9000
```
:::
::::

## Describe a beam

Save this as `beams.yaml`:

```{literalinclude} ../examples/gallery.yaml
:language: yaml
:end-before: "propped_cantilever:"
```

`_environment: structural` lets you write quantities such as `6 m` and
`4.5 kN/m`. Leave it out to use plain numbers in any consistent units.

## Draw it

```python
import beamz9000 as bz

bz.draw("beams.yaml", "simple_udl.png")
```

```{beam-figure} gallery.yaml simple_udl
```

The file suffix picks the format:

| Suffix | Renderer | Notes |
|---|---|---|
| `.svg` | `SVGRenderer` | Native SVG. Labels are `<text>` elements. |
| `.png` | `MatplotlibRenderer` | Raster, 150 dpi by default. |
| `.pdf` | `MatplotlibRenderer` | Fonts embedded as TrueType, so text stays selectable. |

When a file holds several beams, name the one to draw with `beam_id`:

```python
bz.draw("beams.yaml", "B2.pdf", beam_id="B2")
```

## Work with the parsed scheme

`load_scheme` returns a validated {class}`~beamz9000.scheme.Scheme`. Each beam
knows its resolved geometry and loads:

```python
scheme = bz.load_scheme("beams.yaml")
beam = scheme["simple_udl"]

beam.length          # 6.000 m
beam.nodes           # [0.000 m, 6.000 m]
beam.node_supports   # ['pin', 'roller']
for load in beam.resolved_loads:
    print(load.kind, load.case, load.x1, load.x2, load.mag1)
```

A scheme can also come from data you already have:

```python
scheme = bz.parse_scheme({
    "B1": {"spans": [6000], "loads": [{"dist": {"w": 4.5, "case": "D"}}]},
})
```

## Next steps

- {doc}`scheme` describes every key in the format.
- {doc}`gallery` shows common beams with their schemes.
- {doc}`customizing` changes sizes, colours and fonts.
