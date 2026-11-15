"""
Helpers for values that are either plain numbers or forallpeople quantities.

A scheme may be written with plain numbers (any consistent unit system) or with
quantity strs such as "4500 mm" when the file names a forallpeople environment
in `_environment`. These helpers let the rest of the code treat both alike.
"""

from __future__ import annotations

import math
import re
from typing import Any, Union

from forallpeople import Physical
from forallpeople.dimensions import Dimensions

Value = Union[int, float, Physical]


class Quantity(Physical):
    """
    A Physical that remembers the str it was parsed from, so labels show what
    the engineer wrote ("12 kN/mm") rather than forallpeople's choice of units
    ("12 MN/m"). Arithmetic returns plain Physicals, which have no source.
    """

    __slots__ = ("source",)

    def __init__(self, physical: Physical, source: str):
        super().__init__(
            physical.value, physical.dimensions, physical.factor,
            physical.precision, physical.prefixed,
        )
        object.__setattr__(self, "source", " ".join(source.split()))

    @property
    def display(self) -> str:
        """The source typeset: "kN*m" -> "kN·m", "mm**4" -> "mm⁴"."""
        return _typeset(self.source)

    def __reduce__(self):
        plain = Physical(self.value, self.dimensions, self.factor, self.precision, self.prefixed)
        return (Quantity, (plain, self.source))


def keep_sources(raw: Any, parsed: Any) -> Any:
    """
    Returns 'parsed' (the result of forallpeople's parse_tree on 'raw') with
    each Physical that came from a str in 'raw' made a Quantity remembering it.
    """
    if isinstance(parsed, Physical) and isinstance(raw, str):
        return Quantity(parsed, raw)
    if isinstance(parsed, dict) and isinstance(raw, dict):
        return {k: keep_sources(raw.get(k), v) for k, v in parsed.items()}
    if isinstance(parsed, (list, tuple)) and isinstance(raw, (list, tuple)) and len(raw) == len(parsed):
        return type(parsed)(keep_sources(r, v) for r, v in zip(raw, parsed))
    return parsed


def _dims(kg=0, m=0, s=0) -> Dimensions:
    return Dimensions(kg, m, s, 0, 0, 0, 0)


# The dimensions of each kind of quantity a scheme uses, in SI base units.
DIMENSIONS: dict[str, Dimensions] = {
    "length": _dims(m=1),
    "force": _dims(kg=1, m=1, s=-2),
    "line_load": _dims(kg=1, s=-2),
    "pressure": _dims(kg=1, m=-1, s=-2),
    "moment": _dims(kg=1, m=2, s=-2),
    "modulus": _dims(kg=1, m=-1, s=-2),
    "inertia": _dims(m=4),
    "stiffness": _dims(kg=1, m=3, s=-2),
    "spring": _dims(kg=1, s=-2),  # Force per length, e.g. kN/mm.
    "rotational_spring": _dims(kg=1, m=2, s=-2),  # Moment per radian, e.g. kN·m/rad.
}


def is_quantity(value: Any) -> bool:
    """Returns True if 'value' is a forallpeople Physical."""
    return isinstance(value, Physical)


def is_number(value: Any) -> bool:
    """Returns True if 'value' is a plain int or float (bools excluded)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def si(value: Value) -> float:
    """
    Returns 'value' as a float: the SI base-unit value of a Physical, or the
    plain number itself.
    """
    if isinstance(value, Physical):
        return float(value.value)
    return float(value)


def check_kind(value: Any, kind: str) -> Value:
    """
    Returns 'value' if it is a plain number, or a Physical with the dimensions
    of 'kind' (a key of DIMENSIONS). Raises ValueError otherwise.
    """
    if is_number(value):
        return value
    if isinstance(value, Physical):
        expected = DIMENSIONS[kind]
        if value.dimensions != expected:
            raise ValueError(
                f"expected a {kind.replace('_', ' ')} quantity, got {value} "
                f"with the wrong dimensions"
            )
        return value
    if isinstance(value, str):
        raise ValueError(
            f"{value!r} is not a number. Quantity strs such as '4500 mm' need the "
            f"file to name a units environment, e.g. `_environment: structural`."
        )
    raise ValueError(f"expected a number or quantity, got {value!r}")


def add(a: Value, b: Value) -> Value:
    """Returns a + b, where a plain 0 may be added to a Physical."""
    if is_number(a) and a == 0:
        return b
    if is_number(b) and b == 0:
        return a
    return a + b


def scale(a: Value, factor: float) -> Value:
    """Returns a * factor."""
    return a * factor


def is_negative(a: Value) -> bool:
    """Returns True if 'a' is less than zero."""
    return si(a) < 0


def label(value: Value, precision: int = 3) -> str:
    """
    Returns a short display str for 'value': the str it was written as, for a
    Quantity, or else the value with trailing zeros dropped:
    2.500 kN/m -> "2.5 kN/m", 4500.000 mm -> "4500 mm", 2500.0 -> "2500".
    """
    if isinstance(value, Quantity):
        return value.display
    if isinstance(value, Physical):
        text = str(round(value, precision))
        number, _, unit = text.partition(" ")
        return f"{_trim(number)} {unit}".strip()
    return _trim(f"{float(value):.{precision}f}")


def magnitude_label(value: Value, precision: int = 3) -> str:
    """
    Returns label(value) without a sign, or "" for zero: for glyphs, such as
    arrows, that already show the direction.
    """
    if si(value) == 0:
        return ""
    if isinstance(value, Quantity):
        return value.display.lstrip("+-").lstrip()
    return label(abs(value), precision)


_SUPERSCRIPTS = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def _typeset(text: str) -> str:
    """Typesets the unit part of a quantity str: ** as superscripts, * as a middle dot."""
    number, sep, unit = text.partition(" ")
    unit = re.sub(r"\*\*\s*(-?\d+)", lambda m: m.group(1).translate(_SUPERSCRIPTS), unit)
    unit = re.sub(r"\s*\*\s*", "·", unit)
    return f"{number}{sep}{unit}"


def _trim(number: str) -> str:
    if "." in number:
        number = number.rstrip("0").rstrip(".")
    return "0" if number in ("-0", "") else number


# --- Results ------------------------------------------------------------------
#
# Computed results are shown in the units the scheme was written in: a beam
# loaded in kN gets reactions in kN and moments in kN·m. Units per kind, with
# their size in SI base units.
RESULT_UNITS: dict[str, dict[str, float]] = {
    "force": {"N": 1.0, "kN": 1e3, "MN": 1e6, "lb": 4.4482216, "lbf": 4.4482216, "kip": 4448.2216},
    "moment": {
        "N·m": 1.0, "kN·m": 1e3, "MN·m": 1e6,
        "lb·ft": 1.3558179, "lb·in": 0.11298483, "kip·ft": 1355.8179, "kip·in": 112.98483,
    },
    "length": {"mm": 1e-3, "cm": 1e-2, "m": 1.0, "in": 0.0254, "ft": 0.3048},
}
_DEFAULT_RESULT_UNITS = {"force": "kN", "moment": "kN·m", "length": "mm", "rotation": "rad"}
_IMPERIAL_LENGTHS = {"in", "ft"}


def unit_of(value: Any) -> str | None:
    """The typeset unit a Quantity was written in ("kN·m" for "5 kN*m"), or None."""
    if isinstance(value, Quantity):
        return value.display.partition(" ")[2] or None
    return None


def result_units(values: dict[str, list[Any]]) -> dict[str, str]:
    """
    Picks display units for results from the quantities a scheme used:
    'values' maps "force", "moment", "line_load", "pressure" and "length" to
    the values written for each. Forces follow point loads (or the force in a
    line load or pressure unit), moments follow moment loads (or force × the
    span length unit), deflections are mm, or in for imperial spans.
    """
    chosen = dict(_DEFAULT_RESULT_UNITS)
    force = _first_unit(values.get("force", []), RESULT_UNITS["force"])
    if force is None:
        for kind in ("line_load", "pressure"):
            for v in values.get(kind, []):
                unit = unit_of(v) or ""
                head = unit.split("/")[0]
                if head in RESULT_UNITS["force"]:
                    force = head
                elif unit in ("Pa", "kPa", "MPa"):
                    force = {"Pa": "N", "kPa": "kN", "MPa": "MN"}[unit]
                elif unit in ("psf", "psi", "ksf", "ksi"):
                    force = "kip" if unit.startswith("k") else "lb"
                if force:
                    break
            if force:
                break
    if force:
        chosen["force"] = force
    lengths = [unit_of(v) for v in values.get("length", [])]
    imperial = any(u in _IMPERIAL_LENGTHS for u in lengths)
    moment = _first_unit(values.get("moment", []), RESULT_UNITS["moment"])
    if moment is None:
        candidate = f"{chosen['force']}·{'ft' if imperial else 'm'}"
        moment = candidate if candidate in RESULT_UNITS["moment"] else None
    if moment:
        chosen["moment"] = moment
    if imperial:
        chosen["length"] = "in"
    return chosen


def _first_unit(values: list[Any], table: dict[str, float]) -> str | None:
    for v in values:
        unit = unit_of(v)
        if unit in table:
            return unit
    return None


def result_label(value: float, kind: str, unit: str | None, signed: bool = True) -> str:
    """
    Formats a computed SI 'value' in 'unit' (a key of RESULT_UNITS[kind], or
    "rad" for rotations) to three significant figures. With 'unit' None, the
    value is a plain number from a unitless scheme and is shown bare.
    """
    if unit is None:
        return _sig(value if signed else abs(value))
    factor = RESULT_UNITS.get(kind, {}).get(unit, 1.0)
    shown = value / factor
    return f"{_sig(shown if signed else abs(shown))} {unit}"


def _sig(value: float, figures: int = 3) -> str:
    """'value' to 'figures' significant figures, without exponent notation."""
    if value == 0:
        return "0"
    digits = max(0, figures - 1 - int(math.floor(math.log10(abs(value)))))
    text = f"{value:.{digits}f}"
    return _trim(text).replace("-", "−")
