"""
Pydantic models for the beam scheme YAML format.

A scheme file maps beam ids to beam definitions. Values may be plain numbers
(any consistent unit system) or, when the file names a forallpeople environment
with `_environment: structural` (for example), quantity strs like "4500 mm".

    _environment: structural
    B1:
      spans: [4500 mm, 2500 mm]
      cantilever: right
      loads:
        - point: {p: 15 kN, span_loc: [1, 1250 mm], case: L}
        - dist: {mag: 2.5 kN/m, case: D}

Conventions
-----------
- Locations are measured from the left end of the beam.
- A negative `loc` is measured back from the right end (L - |loc|), and `L`
  means the right end. A negative span offset is measured back from the end of
  that span, and `S` means the end of the span.
- `span_loc: [i, offset]` locates a point within span i (0-based). A bare
  integer `span_loc: i` means the end of span i.
- Positive force magnitudes act downward (gravity). Positive moments are
  counter-clockwise. A point load's `angle` (degrees from vertical) tilts its
  tail counter-clockwise about its tip when positive.
- A load without a `case` is an already-factored load.
"""

from __future__ import annotations

import pathlib
import warnings
from functools import cached_property
from typing import Annotated, Any, Literal, Optional, Union

import yaml
from pydantic import (
    AfterValidator,
    AliasChoices,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    model_validator,
)

from beamz9000 import units
from beamz9000.units import Value

ENVIRONMENT_KEY = "_environment"


def _kind(kind: str):
    return AfterValidator(lambda v: units.check_kind(v, kind))


# A plain number or a Physical of the named kind.
Length = Annotated[Any, _kind("length")]
Force = Annotated[Any, _kind("force")]
LineLoad = Annotated[Any, _kind("line_load")]
Pressure = Annotated[Any, _kind("pressure")]
Moment = Annotated[Any, _kind("moment")]
Modulus = Annotated[Any, _kind("modulus")]
Inertia = Annotated[Any, _kind("inertia")]
Stiffness = Annotated[Any, _kind("stiffness")]


def _location(value: Any) -> Any:
    if value == "L":
        return value
    return units.check_kind(value, "length")


def _span_location(value: Any) -> Any:
    """Normalizes a span location to (span index, offset or 'S')."""
    if units.is_number(value) and int(value) == value:
        return (int(value), "S")
    if isinstance(value, (list, tuple)) and len(value) == 2:
        idx, offset = value
        if not (units.is_number(idx) and int(idx) == idx):
            raise ValueError(f"the span index in {list(value)} must be an integer")
        if offset != "S":
            offset = units.check_kind(offset, "length")
        return (int(idx), offset)
    raise ValueError(
        f"a span location is [span index, offset] or a span index alone, got {value!r}"
    )


# A global location: a length (negative from the right end) or "L".
Location = Annotated[Any, AfterValidator(_location)]
# (span index, offset or "S"); a bare index means the end of that span.
SpanLocation = Annotated[Any, AfterValidator(_span_location)]

SupportType = Literal["pin", "roller", "fixed", "free", "spring", "rotational_spring"]
_SUPPORT_ALIASES = {
    "pinned": "pin", "hinge": "pin", "fix": "fixed", "none": "free",
    "v_spring": "spring", "vertical_spring": "spring",
    "m_spring": "rotational_spring", "rot_spring": "rotational_spring",
}
Diagram = Literal["moment", "shear", "deflection", "rotation"]


class _Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid", populate_by_name=True, arbitrary_types_allowed=True
    )


def _single_key_items(value: Any, what: str) -> Any:
    """
    Merges a list of single-key mappings (`- name: {...}`) into one mapping.
    A mapping is returned as is.
    """
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        merged = {}
        for item in value:
            if not isinstance(item, dict) or len(item) != 1:
                raise ValueError(f"each item in {what} must be a single `name: ...` mapping, got {item!r}")
            (key, val), = item.items()
            if key in merged:
                raise ValueError(f"{key!r} appears twice in {what}")
            merged[key] = val
        return merged
    raise ValueError(f"{what} must be a mapping or a list of `name: ...` mappings")


# --- Loads -----------------------------------------------------------------


class _Load(_Model):
    case: Optional[str] = Field(None, description="Load case; None means already factored.")
    label: Optional[str] = Field(None, description="Overrides the drawn magnitude label.")


class _PointLike(_Load):
    loc: Optional[Location] = Field(None, validation_alias=AliasChoices("loc", "x"))
    span_loc: Optional[SpanLocation] = None

    @model_validator(mode="after")
    def _one_location(self):
        if (self.loc is None) == (self.span_loc is None):
            raise ValueError("give exactly one of `loc` (alias `x`) or `span_loc`")
        return self


class PointLoad(_PointLike):
    """
    A concentrated force. Positive acts downward. `angle` is in degrees from
    vertical: positive tilts the arrow's tail counter-clockwise about its tip.
    """

    type: Literal["point"] = "point"
    mag: Force = Field(validation_alias=AliasChoices("mag", "magnitude", "p"))
    angle: float = Field(0.0, ge=-90, le=90, validation_alias=AliasChoices("angle", "alpha"))


class MomentLoad(_PointLike):
    """A concentrated moment. Positive is counter-clockwise."""

    type: Literal["moment"] = "moment"
    mag: Moment = Field(validation_alias=AliasChoices("mag", "magnitude", "m"))


class _Extent(_Load):
    """A load over a region. With no start or end given it covers the whole beam."""

    loc1: Optional[Location] = Field(None, validation_alias=AliasChoices("loc1", "x1"))
    loc2: Optional[Location] = Field(None, validation_alias=AliasChoices("loc2", "x2"))
    span_loc1: Optional[SpanLocation] = None
    span_loc2: Optional[SpanLocation] = None

    @model_validator(mode="after")
    def _one_location_each(self):
        for n in ("1", "2"):
            if getattr(self, f"loc{n}") is not None and getattr(self, f"span_loc{n}") is not None:
                raise ValueError(f"give at most one of `loc{n}` (alias `x{n}`) or `span_loc{n}`")
        return self


def _uniform(names: tuple[str, str], *aliases: str):
    """Spreads a single uniform value (under any of 'aliases') to both 'names'."""

    def spread(data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        found = [a for a in aliases if a in data]
        if not found:
            return data
        if len(found) > 1 or any(n in data for n in names):
            raise ValueError(f"give either `{found[0]}` or `{names[0]}`/`{names[1]}`, not both")
        data = dict(data)
        value = data.pop(found[0])
        return {**data, names[0]: value, names[1]: value}

    return spread


class DistLoad(_Extent):
    """A uniform (`mag`) or linearly varying (`mag1` -> `mag2`) line load."""

    type: Literal["dist"] = "dist"
    mag1: LineLoad
    mag2: Optional[LineLoad] = None

    @model_validator(mode="before")
    @classmethod
    def _spread_uniform(cls, data):
        return _uniform(("mag1", "mag2"), "mag", "magnitude", "w")(data)

    @model_validator(mode="after")
    def _default_mag2(self):
        if self.mag2 is None:
            self.mag2 = self.mag1
        return self


class PressureLoad(_Extent):
    """
    An area load over a tributary width, giving a line load of
    mag × trib_width that may vary from trib_width1 to trib_width2.

    `mag` may name an occupancy instead of a pressure: the load then stands for
    one pressure per load case in that occupancy (or only `case`, if given).
    """

    type: Literal["pressure"] = "pressure"
    mag: Union[Pressure, str] = Field(
        validation_alias=AliasChoices("mag", "magnitude", "q", "occupancy")
    )
    trib_width1: Length
    trib_width2: Optional[Length] = None

    @model_validator(mode="before")
    @classmethod
    def _spread_uniform(cls, data):
        return _uniform(("trib_width1", "trib_width2"), "trib_width", "trib")(data)

    @model_validator(mode="after")
    def _default_trib2(self):
        if self.trib_width2 is None:
            self.trib_width2 = self.trib_width1
        return self

    @property
    def occupancy(self) -> Optional[str]:
        return self.mag if isinstance(self.mag, str) else None


def _tag_load(value: Any) -> Any:
    """Turns `{point: {...}}` into `{type: point, ...}` for the discriminated union."""
    if isinstance(value, dict) and "type" not in value and len(value) == 1:
        (kind, body), = value.items()
        return {"type": kind, **(body or {})}
    return value


Load = Annotated[
    Annotated[
        Union[PointLoad, MomentLoad, DistLoad, PressureLoad],
        Field(discriminator="type"),
    ],
    BeforeValidator(_tag_load),
]


# --- Combinations, occupancies, results -----------------------------------------


def _combo(value: Any) -> Any:
    """
    Normalizes a load combination to {case: factor}. Accepted forms:
    `{name: D, factor: 1.4}`, a list of those, or `{D: 1.25, L: 1.5}`.
    """
    if isinstance(value, dict) and set(value) == {"name", "factor"}:
        return {value["name"]: value["factor"]}
    if isinstance(value, list):
        merged = {}
        for item in value:
            merged.update(_combo(item))
        return merged
    return value


class Results(_Model):
    diagrams: list[Diagram] = Field(default_factory=list)
    combos: Optional[list[str]] = Field(
        None, description="Combinations to show; all of them if not given."
    )

    @model_validator(mode="before")
    @classmethod
    def _merge_items(cls, data):
        # Accepts `- diagrams: [...]` (a list of single-key items) as well as a mapping.
        if isinstance(data, list):
            return _single_key_items(data, "results")
        return data


# --- Resolved loads ---------------------------------------------------------


class ResolvedLoad(_Model):
    """A load with its location(s) resolved to distances from the left end."""

    kind: Literal["point", "moment", "line"]
    source: Literal["point", "moment", "dist", "pressure"]
    index: int = Field(description="Position of the source load in `loads`.")
    case: Optional[str]
    occupancy: Optional[str] = None
    x1: Value
    x2: Optional[Value] = None
    mag1: Value
    mag2: Optional[Value] = None
    label: Optional[str] = None
    pressure: Optional[Value] = Field(None, description="For pressure loads: the area load.")
    angle: float = Field(0.0, description="For point loads: degrees from vertical.")


# --- Supports -----------------------------------------------------------------


class Support(_Model):
    """
    A support at a node. Springs may give a stiffness `k`: force per length
    for a `spring`, moment per radian for a `rotational_spring`. A rotational
    spring also restrains translation, like a pin.
    """

    type: SupportType
    k: Optional[Any] = None

    @model_validator(mode="after")
    def _check_k(self):
        if self.k is not None:
            if self.type not in ("spring", "rotational_spring"):
                raise ValueError(f"only springs take a stiffness `k`, not a {self.type}")
            units.check_kind(self.k, self.type)
        return self


def _support_item(value: Any) -> Any:
    """
    Normalizes a support to {type, k}. Accepted forms: "pin", {type: spring,
    k: 5 kN/mm}, or {spring: 5 kN/mm}.
    """
    if isinstance(value, Support):
        return value
    if isinstance(value, str):
        value = {"type": value}
    elif isinstance(value, dict) and "type" not in value and len(value) == 1:
        (kind, k), = value.items()
        value = {"type": kind, "k": k}
    if isinstance(value, dict) and isinstance(value.get("type"), str):
        kind = value["type"].strip().lower()
        value = {**value, "type": _SUPPORT_ALIASES.get(kind, kind)}
    return value


SupportIn = Annotated[Support, BeforeValidator(_support_item)]


# --- Beam ---------------------------------------------------------------------


class Beam(_Model):
    """One beam: its spans, supports, stiffness, loads and what to report."""

    spans: list[Length] = Field(min_length=1)
    cantilever: Optional[Literal["left", "right", "both"]] = None
    e: Optional[Modulus] = None
    i: Optional[Inertia] = None
    ei: Optional[Stiffness] = None
    supports: Optional[Union[list[SupportIn], dict[int, SupportIn]]] = Field(
        None,
        description=(
            "Overrides the assumed supports: one per node (spans + 1), "
            "or {node index: support} for just the nodes that differ."
        ),
    )
    depth: Optional[Length] = Field(None, description="Drawn depth of the beam; a line if not given.")
    node_labels: Optional[Union[Literal["auto"], list[Optional[str]]]] = Field(
        None,
        validation_alias=AliasChoices("node_labels", "labels"),
        description="One label per node (null to skip one), or `auto` for A, B, C, ...",
    )
    loads: list[Load] = Field(default_factory=list)
    occupancies: dict[str, dict[str, Pressure]] = Field(default_factory=dict)
    load_combos: dict[str, dict[str, float]] = Field(default_factory=dict)
    results: Results = Field(default_factory=Results)

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data):
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "occupancies" in data:
            data["occupancies"] = _single_key_items(data["occupancies"], "occupancies")
        if "load_combos" in data:
            combos = _single_key_items(data["load_combos"], "load_combos")
            data["load_combos"] = {k: _combo(v) for k, v in combos.items()}
        if data.get("loads") is None:
            data.pop("loads", None)
        for key in ("supports", "e", "i", "ei", "cantilever", "results", "depth", "node_labels", "labels"):
            if key in data and (data[key] is None or data[key] is ... or data[key] == "..."):
                data.pop(key)
        return data

    @model_validator(mode="after")
    def _check(self):
        for idx, span in enumerate(self.spans):
            if units.si(span) <= 0:
                raise ValueError(f"span {idx} must be positive, got {units.label(span)}")
        if self.ei is not None and (self.e is not None or self.i is not None):
            raise ValueError("give either `ei` or both `e` and `i`, not both")
        if (self.e is None) != (self.i is None):
            raise ValueError("`e` and `i` must be given together (or give `ei`)")
        self._check_supports()
        self._check_units()
        if self.depth is not None and units.si(self.depth) <= 0:
            raise ValueError(f"`depth` must be positive, got {units.label(self.depth)}")
        if isinstance(self.node_labels, list) and len(self.node_labels) != len(self.spans) + 1:
            raise ValueError(
                f"`node_labels` lists {len(self.node_labels)} labels but the beam has "
                f"{len(self.spans) + 1} nodes"
            )
        if self.cantilever == "both" and len(self.spans) < 3:
            raise ValueError("`cantilever: both` needs at least 3 spans")
        self._check_occupancies()
        _ = self.resolved_loads
        if self.stiffness is None and {"deflection", "rotation"} & set(self.results.diagrams):
            warnings.warn(
                "deflection and rotation diagrams need `e` and `i` (or `ei`); they will be skipped",
                stacklevel=2,
            )
        return self

    def _check_units(self):
        """A beam must use quantities throughout or plain numbers throughout."""
        values = list(self.spans) + [self.e, self.i, self.ei, self.depth]
        values += [s.k for s in self.support_specs]
        for load in self.loads:
            values += [v for k, v in load if k.startswith(("mag", "loc", "trib")) and not isinstance(v, str)]
            values += [v[1] for k, v in load if k.startswith("span_loc") and v is not None]
        for pressures in self.occupancies.values():
            values += list(pressures.values())
        values = [v for v in values if v is not None and v not in ("L", "S")]
        has_quantity = any(units.is_quantity(v) for v in values)
        bare = [v for v in values if units.is_number(v) and v != 0]
        if has_quantity and bare:
            raise ValueError(
                f"this beam mixes quantities with plain numbers (e.g. {bare[0]!r}); "
                f"give every value a unit, or none"
            )

    def _check_supports(self):
        n_nodes = len(self.spans) + 1
        if isinstance(self.supports, list) and len(self.supports) != n_nodes:
            raise ValueError(
                f"`supports` lists {len(self.supports)} supports but the beam has {n_nodes} nodes"
            )
        if isinstance(self.supports, dict):
            bad = [k for k in self.supports if not 0 <= k < n_nodes]
            if bad:
                raise ValueError(f"`supports` names node {bad[0]} but nodes run 0 to {n_nodes - 1}")
        types = self.node_supports
        if self.supports is not None and self.cantilever is not None:
            ends = {"left": [0], "right": [-1], "both": [0, -1]}[self.cantilever]
            if any(types[e] != "free" for e in ends):
                raise ValueError(
                    f"`cantilever: {self.cantilever}` conflicts with `supports`, "
                    f"which does not leave that end free"
                )
        restrained = [t for t in types if t != "free"]
        horizontal = {"pin", "fixed", "rotational_spring"} & set(types)
        if not ("fixed" in types or (len(restrained) >= 2 and horizontal)):
            warnings.warn(f"the supports {types} do not make a stable beam", stacklevel=3)

    def _check_occupancies(self):
        for idx, load in enumerate(self.loads):
            if isinstance(load, PressureLoad) and load.occupancy is not None:
                occ = self.occupancies.get(load.occupancy)
                if occ is None:
                    raise ValueError(
                        f"load {idx} names the occupancy {load.occupancy!r}, which is not "
                        f"in `occupancies` ({', '.join(self.occupancies) or 'none given'})"
                    )
                if load.case is not None and load.case not in occ:
                    raise ValueError(
                        f"load {idx} picks case {load.case!r} from occupancy "
                        f"{load.occupancy!r}, which has only {', '.join(occ)}"
                    )

    # --- Derived geometry ---

    @property
    def length(self) -> Value:
        total = 0
        for span in self.spans:
            total = units.add(total, span)
        return total

    @property
    def nodes(self) -> list[Value]:
        """Locations of the span ends, from the left end."""
        locs = [units.scale(self.spans[0], 0)]
        for span in self.spans:
            locs.append(units.add(locs[-1], span))
        return locs

    @property
    def stiffness(self) -> Optional[Value]:
        """EI, if given directly or as `e` and `i`."""
        if self.ei is not None:
            return self.ei
        if self.e is not None and self.i is not None:
            return self.e * self.i
        return None

    @property
    def node_supports(self) -> list[SupportType]:
        """The support type at each node (see `support_specs`)."""
        return [s.type for s in self.support_specs]

    @property
    def support_specs(self) -> list[Support]:
        """
        The support at each node. Unless overridden, a pin at the first
        supported node and rollers at the others, with cantilevered ends free.
        A single span with one cantilevered end is fixed at the other end.
        """
        if isinstance(self.supports, list):
            return list(self.supports)
        n = len(self.spans) + 1
        free = {"left": {0}, "right": {n - 1}, "both": {0, n - 1}}.get(self.cantilever, set())
        if len(self.spans) == 1 and len(free) == 1:
            types = ["free" if i in free else "fixed" for i in range(n)]
        else:
            types, pinned = [], False
            for i in range(n):
                if i in free:
                    types.append("free")
                else:
                    types.append("roller" if pinned else "pin")
                    pinned = True
        specs = [Support(type=t) for t in types]
        if isinstance(self.supports, dict):
            for idx, support in self.supports.items():
                specs[idx] = support
        return specs

    @property
    def labels(self) -> list[Optional[str]]:
        """The label at each node: A, B, C, ... with `node_labels: auto`."""
        n = len(self.spans) + 1
        if self.node_labels == "auto":
            return [_letters(i) for i in range(n)]
        if self.node_labels is None:
            return [None] * n
        return list(self.node_labels)

    # --- Locations ---

    def resolve_location(self, loc: Any) -> Value:
        """Returns the distance from the left end for a global `loc`."""
        if loc == "L":
            return self.length
        if units.is_negative(loc):
            return units.add(self.length, loc)
        return loc

    def resolve_span_location(self, span_loc: tuple[int, Any]) -> Value:
        """Returns the distance from the left end for a (span index, offset)."""
        idx, offset = span_loc
        if not 0 <= idx < len(self.spans):
            raise ValueError(f"span index {idx} is out of range: the beam has {len(self.spans)} spans")
        start, span = self.nodes[idx], self.spans[idx]
        if offset == "S":
            return units.add(start, span)
        if units.is_negative(offset):
            offset = units.add(span, offset)
        if units.si(offset) > units.si(span) + 1e-9 * max(1.0, abs(units.si(span))):
            raise ValueError(
                f"offset {units.label(offset)} is beyond the end of span {idx} ({units.label(span)})"
            )
        return units.add(start, offset)

    def _resolve(self, loc, span_loc, default):
        if loc is not None:
            return self.resolve_location(loc)
        if span_loc is not None:
            return self.resolve_span_location(span_loc)
        return default

    @cached_property
    def resolved_loads(self) -> list[ResolvedLoad]:
        """
        Every load with resolved locations. A pressure load naming an occupancy
        becomes one line load per case in that occupancy.
        """
        out = []
        length = units.si(self.length)
        start, end = self.nodes[0], self.length
        for idx, load in enumerate(self.loads):
            try:
                out += self._resolve_one(idx, load, start, end)
            except ValueError as err:
                raise ValueError(f"load {idx} ({load.type}): {err}") from None
        for r in out:
            for x in (r.x1, r.x2):
                if x is not None and not -1e-9 <= units.si(x) / length <= 1 + 1e-9:
                    raise ValueError(
                        f"load {r.index} ({r.source}) at {units.label(x)} is off the beam "
                        f"(length {units.label(self.length)})"
                    )
        return out

    def _resolve_one(self, idx, load, start, end) -> list[ResolvedLoad]:
        common = dict(index=idx, case=load.case, label=load.label, source=load.type)
        if isinstance(load, (PointLoad, MomentLoad)):
            x = self._resolve(load.loc, load.span_loc, None)
            angle = getattr(load, "angle", 0.0)
            return [ResolvedLoad(kind=load.type, x1=x, mag1=load.mag, angle=angle, **common)]
        x1 = self._resolve(load.loc1, load.span_loc1, start)
        x2 = self._resolve(load.loc2, load.span_loc2, end)
        if units.si(x2) <= units.si(x1):
            raise ValueError(f"it must end after it starts ({units.label(x1)} to {units.label(x2)})")
        if isinstance(load, DistLoad):
            return [ResolvedLoad(kind="line", x1=x1, x2=x2, mag1=load.mag1, mag2=load.mag2, **common)]
        if load.occupancy is None:
            pressures = {load.case: load.mag}
            occupancy = None
        else:
            occ = self.occupancies[load.occupancy]
            pressures = {load.case: occ[load.case]} if load.case else dict(occ)
            occupancy = load.occupancy
        return [
            ResolvedLoad(
                kind="line", x1=x1, x2=x2,
                mag1=q * load.trib_width1, mag2=q * load.trib_width2, pressure=q,
                **{**common, "case": case, "occupancy": occupancy},
            )
            for case, q in pressures.items()
        ]


def _letters(i: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA, ..."""
    out = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        out = chr(65 + r) + out
    return out


# --- Scheme file -------------------------------------------------------------


class Scheme(_Model):
    """A scheme file: beams keyed by id, and the units environment if named."""

    environment: Optional[str] = None
    beams: dict[str, Beam]

    def __getitem__(self, beam_id: str) -> Beam:
        return self.beams[beam_id]

    def __iter__(self):
        return iter(self.beams.items())


def parse_scheme(data: dict) -> Scheme:
    """
    Returns a Scheme from already-loaded YAML/JSON data. If 'data' names a
    forallpeople environment in `_environment`, quantity strs are parsed first.
    """
    if not isinstance(data, dict):
        raise ValueError("a scheme must be a mapping of beam ids to beams")
    data = dict(data)
    env = data.pop(ENVIRONMENT_KEY, None)
    if env is not None:
        import forallpeople as fp

        fp.environment(env, top_level=False)
        data = units.keep_sources(data, fp.parse_tree(data, strict=True))
    return Scheme(environment=env, beams=data)


def load_scheme(source: Union[str, pathlib.Path]) -> Scheme:
    """
    Returns a Scheme read from 'source': a path to a YAML file, or YAML text.
    """
    if isinstance(source, pathlib.Path) or (
        isinstance(source, str) and "\n" not in source and source.endswith((".yml", ".yaml"))
    ):
        text = pathlib.Path(source).read_text(encoding="utf-8")
    else:
        text = source
    return parse_scheme(yaml.safe_load(text))
