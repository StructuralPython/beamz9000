"""
Helpers for values that are either plain numbers or forallpeople quantities.

A scheme may be written with plain numbers (any consistent unit system) or with
quantity strs such as "4500 mm" when the file names a forallpeople environment
in `_environment`. These helpers let the rest of the code treat both alike.
"""

from __future__ import annotations

from typing import Any, Union

from forallpeople import Physical
from forallpeople.dimensions import Dimensions

Number = Union[int, float]
Value = Union[int, float, Physical]


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


def neg(a: Value) -> Value:
    """Returns -a."""
    return -a


def scale(a: Value, factor: float) -> Value:
    """Returns a * factor."""
    return a * factor


def is_negative(a: Value) -> bool:
    """Returns True if 'a' is less than zero."""
    return si(a) < 0


def label(value: Value, precision: int = 3) -> str:
    """
    Returns a short display str for 'value', with trailing zeros dropped:
    2.500 kN/m -> "2.5 kN/m", 4500.000 mm -> "4500 mm", 2500.0 -> "2500".
    """
    if isinstance(value, Physical):
        text = str(value.round(precision))
        number, _, unit = text.partition(" ")
        return f"{_trim(number)} {unit}".strip()
    return _trim(f"{float(value):.{precision}f}")


def _trim(number: str) -> str:
    if "." in number:
        number = number.rstrip("0").rstrip(".")
    return "0" if number in ("-0", "") else number
