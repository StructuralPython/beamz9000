"""
Styled wrappers around shapely geometry.

shapely geometry carries no colour, line weight, line type, opacity, hatch,
z-order or text. The elements here pair geometry with that information so a
diagram can be built entirely from shapely operations, then handed to any
renderer.

Three element kinds exist:

- `Shape`: any shapely geometry, with `Stroke` and `Fill` styles.
- `Text`: a string at an anchor point, with `Font` and `Fill` styles. Text
  stays text: renderers draw it as native, searchable text. `graphics.text`
  measures it with libraqm shaping so layout reserves exactly its space.
- `Group`: an ordered collection of elements, for composition only.

Elements are frozen. Transforms (`translate`, `rotate`, `scale`, `mirror_x`,
`mirror_y`) and `restyle` return new elements and walk into groups. Elements
serialize to JSON, with geometry written as GeoJSON-like mappings, and read
back equal.
"""

from __future__ import annotations

from typing import Annotated, Any, Iterator, Literal, Optional, Union

import shapely
from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, PlainValidator
from shapely import affinity
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry


def _to_geometry(value: Any) -> BaseGeometry:
    if isinstance(value, BaseGeometry):
        return value
    if isinstance(value, dict):
        return shape(value)
    raise ValueError(f"expected a shapely geometry or a GeoJSON-like mapping, got {type(value).__name__}")


def _listify(obj: Any) -> Any:
    if isinstance(obj, (tuple, list)):
        return [_listify(o) for o in obj]
    if isinstance(obj, dict):
        return {k: _listify(v) for k, v in obj.items()}
    return obj


# Any shapely geometry; serialized as a GeoJSON-like mapping with exact floats.
Geometry = Annotated[
    BaseGeometry,
    PlainValidator(_to_geometry),
    PlainSerializer(lambda g: _listify(mapping(g)), return_type=dict),
]

Color = Optional[str]  # Any matplotlib colour spec ("black", "#0072B2", "tab:red"); None = not drawn.
LineType = Literal["solid", "dashed", "dotted", "dashdot"]
HAlign = Literal["left", "center", "right"]
VAlign = Literal["baseline", "bottom", "center", "top"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True, extra="forbid")


# --- Style mixins -------------------------------------------------------------
# Each mixin holds one family of attributes. Fields are keyword-only in use,
# so the order in which mixins are combined does not matter.


class Stroke(_Frozen):
    """How lines and outlines are drawn. Widths are in points."""

    stroke_color: Color = "black"
    stroke_opacity: float = Field(1.0, ge=0, le=1)
    stroke_width: float = Field(1.0, ge=0)
    line_type: LineType = "solid"


class Fill(_Frozen):
    """
    How closed areas (and text) are filled. `hatch` is a matplotlib-style
    hatch pattern ("/", "\\\\", "x", "-", "+", "o", ".", ...), drawn in the
    stroke colour over the fill.
    """

    fill_color: Color = None
    fill_opacity: float = Field(1.0, ge=0, le=1)
    hatch: Optional[str] = None


class Font(_Frozen):
    """The font a Text is shaped with. `font_size` is in drawing units (em height)."""

    font_family: str = "DejaVu Sans"
    font_size: float = Field(1.0, gt=0)
    font_weight: Literal["normal", "bold"] = "normal"
    font_style: Literal["normal", "italic"] = "normal"


STYLE_FIELDS = set(Stroke.model_fields) | set(Fill.model_fields) | set(Font.model_fields)


# --- Elements -----------------------------------------------------------------


class Element(_Frozen):
    """
    Fields common to every element.

    z: drawing order; higher draws on top. Ties keep insertion order.
    key: the legend key (load case, occupancy, ...) this element belongs to.
    role: what the element is ("beam", "support", "load", "dimension", ...).
    """

    z: float = 0
    key: Optional[str] = None
    role: Optional[str] = None

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        raise NotImplementedError


class Shape(Element, Stroke, Fill):
    """Any shapely geometry with stroke and fill styles."""

    kind: Literal["shape"] = "shape"
    geometry: Geometry

    @property
    def bounds(self):
        return self.geometry.bounds

    @property
    def is_empty(self) -> bool:
        return self.geometry.is_empty


class Text(Element, Font, Fill):
    """
    A single line of text whose alignment point is `anchor`. Text is filled
    (default black) and not stroked. `rotation` is in degrees, counter-clockwise.
    """

    kind: Literal["text"] = "text"
    text: str
    anchor: tuple[float, float] = (0.0, 0.0)
    ha: HAlign = "center"
    va: VAlign = "baseline"
    rotation: float = 0.0
    fill_color: Color = "black"

    @property
    def bounds(self):
        from beamz9000.graphics import text as shaping

        return shaping.text_bounds(self)



class Group(Element):
    """An ordered collection of elements. Groups compose; they are never drawn."""

    kind: Literal["group"] = "group"
    children: list[Annotated[Union[Shape, Text, "Group"], Field(discriminator="kind")]] = Field(
        default_factory=list
    )

    @property
    def bounds(self):
        boxes = [c.bounds for c in self.children if not _empty(c)]
        if not boxes:
            return (0.0, 0.0, 0.0, 0.0)
        return (
            min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes),
        )

    def __iter__(self) -> Iterator[Element]:
        return iter(self.children)

    def __len__(self) -> int:
        return len(self.children)

    def __add__(self, other: Union[Element, list]) -> "Group":
        extra = other if isinstance(other, list) else [other]
        return self.model_copy(update={"children": [*self.children, *extra]})


AnyElement = Union[Shape, Text, Group]


def _empty(el: Element) -> bool:
    if isinstance(el, Shape):
        return el.is_empty
    if isinstance(el, Group):
        return all(_empty(c) for c in el.children)
    return not el.text


def group(*children: Union[Element, list, None], **fields) -> Group:
    """Returns a Group of 'children', flattening lists and skipping None."""
    flat = []
    for child in children:
        if child is None:
            continue
        if isinstance(child, list):
            flat.extend(c for c in child if c is not None)
        else:
            flat.append(child)
    return Group(children=flat, **fields)


def flatten(el: Element) -> list[Union[Shape, Text]]:
    """
    Returns the leaves (Shapes and Texts) under 'el' in drawing order: sorted
    by z, ties kept in tree order. Empty shapes are dropped.
    """
    leaves: list[Union[Shape, Text]] = []

    def walk(e):
        if isinstance(e, Group):
            for c in e.children:
                walk(c)
        elif not _empty(e):
            leaves.append(e)

    walk(el)
    return sorted(leaves, key=lambda leaf: leaf.z)


# --- Functional transforms --------------------------------------------------------


def _map(el: Element, on_shape, on_text) -> Element:
    if isinstance(el, Group):
        return el.model_copy(update={"children": [_map(c, on_shape, on_text) for c in el.children]})
    if isinstance(el, Shape):
        return el.model_copy(update={"geometry": on_shape(el.geometry)})
    if isinstance(el, Text):
        return el.model_copy(update=on_text(el))
    raise TypeError(f"not an element: {el!r}")


def translate(el: Element, dx: float = 0.0, dy: float = 0.0) -> Element:
    """Returns 'el' moved by (dx, dy)."""
    return _map(
        el,
        lambda g: affinity.translate(g, dx, dy),
        lambda t: {"anchor": (t.anchor[0] + dx, t.anchor[1] + dy)},
    )


def rotate(el: Element, angle: float, origin=(0.0, 0.0), turn_text: bool = False) -> Element:
    """
    Returns 'el' rotated 'angle' degrees counter-clockwise about 'origin'.
    Text anchors move with the geometry; text itself stays upright unless
    'turn_text' is True.
    """

    def text(t: Text):
        anchor = affinity.rotate(shapely.Point(t.anchor), angle, origin=origin).coords[0]
        update = {"anchor": tuple(anchor)}
        if turn_text:
            update["rotation"] = t.rotation + angle
        return update

    return _map(el, lambda g: affinity.rotate(g, angle, origin=origin), text)


def scale(el: Element, factor: float, origin=(0.0, 0.0)) -> Element:
    """Returns 'el' scaled uniformly by 'factor' about 'origin'; font sizes scale too."""

    def text(t: Text):
        anchor = affinity.scale(shapely.Point(t.anchor), factor, factor, origin=origin).coords[0]
        return {"anchor": tuple(anchor), "font_size": t.font_size * abs(factor)}

    return _map(el, lambda g: affinity.scale(g, factor, factor, origin=origin), text)


def mirror_x(el: Element, x: float = 0.0) -> Element:
    """Returns 'el' mirrored across the vertical line at 'x'. Text stays readable."""
    flip = {"left": "right", "right": "left", "center": "center"}
    return _map(
        el,
        lambda g: affinity.scale(g, -1, 1, origin=(x, 0)),
        lambda t: {"anchor": (2 * x - t.anchor[0], t.anchor[1]), "ha": flip[t.ha]},
    )


def mirror_y(el: Element, y: float = 0.0) -> Element:
    """Returns 'el' mirrored across the horizontal line at 'y'. Text stays readable."""
    return _map(
        el,
        lambda g: affinity.scale(g, 1, -1, origin=(0, y)),
        lambda t: {"anchor": (t.anchor[0], 2 * y - t.anchor[1])},
    )


def restyle(el: Element, **style) -> Element:
    """
    Returns 'el' with the given style (and z/key/role) fields replaced on every
    leaf that has them. Unknown field names raise ValueError.
    """
    allowed = STYLE_FIELDS | {"z", "key", "role"}
    unknown = set(style) - allowed
    if unknown:
        raise ValueError(f"unknown style fields: {', '.join(sorted(unknown))}")

    def apply(e: Element) -> Element:
        if isinstance(e, Group):
            own = {k: v for k, v in style.items() if k in ("z", "key", "role")}
            return e.model_copy(update={**own, "children": [apply(c) for c in e.children]})
        update = {k: v for k, v in style.items() if k in type(e).model_fields}
        data = {**e.model_dump(exclude={"geometry"}), **update}
        if isinstance(e, Shape):
            data["geometry"] = e.geometry
        return type(e).model_validate(data)  # Validates the new style values.

    return apply(el)


def unite(*geoms: BaseGeometry) -> BaseGeometry:
    """Returns the union of the non-empty geometries in 'geoms'."""
    parts = [g for g in geoms if g is not None and not g.is_empty]
    if not parts:
        return shapely.GeometryCollection()
    return shapely.union_all(parts)
