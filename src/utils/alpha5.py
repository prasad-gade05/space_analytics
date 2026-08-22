"""Bidirectional Alpha-5 catalog-number codec.

Space-Track rule (verified against Space-Track documentation, 2026-08):
catalog numbers above 99999 are written in a 5-character field where the
first character is a letter encoding the ten-thousands digit:
    A=10, B=11, ..., H=17, J=18 (I skipped), K=19, ..., N=22,
    P=23 (O skipped), Q=24, ..., Z=33
Ceiling: Z9999 = 339,999. Numbers below 100000 use plain 5-digit form.
"""

from __future__ import annotations

ALPHA5_CEILING = 339_999

_LETTER_TO_VALUE: dict[str, int] = {}
_value = 10
for _code in range(ord("A"), ord("Z") + 1):
    _letter = chr(_code)
    if _letter in ("I", "O"):
        continue
    _LETTER_TO_VALUE[_letter] = _value
    _value += 1

_VALUE_TO_LETTER: dict[int, str] = {v: k for k, v in _LETTER_TO_VALUE.items()}


def alpha5_decode(code: str) -> int:
    """Decode a 5-character catalog field ('04499' or 'A1234') to integer."""
    code = code.strip().upper()
    if len(code) != 5:
        raise ValueError(f"Alpha-5 field must be exactly 5 characters: {code!r}")
    first = code[0]
    if first.isdigit():
        return int(code)
    if first not in _LETTER_TO_VALUE:
        raise ValueError(f"Invalid Alpha-5 leading character {first!r} in {code!r} "
                         f"(I and O are never used)")
    rest = code[1:]
    if not rest.isdigit():
        raise ValueError(f"Alpha-5 tail must be digits: {code!r}")
    value = _LETTER_TO_VALUE[first] * 10_000 + int(rest)
    if value > ALPHA5_CEILING:
        raise ValueError(f"{value:,} exceeds the Alpha-5 ceiling of {ALPHA5_CEILING:,}")
    return value


def alpha5_encode(catalog_number: int) -> str:
    """Encode an integer NORAD catalog number to its 5-character field."""
    if catalog_number < 0:
        raise ValueError("Catalog numbers cannot be negative")
    if catalog_number > ALPHA5_CEILING:
        raise ValueError(f"{catalog_number:,} exceeds the Alpha-5 ceiling of {ALPHA5_CEILING:,}")
    if catalog_number < 100_000:
        return f"{catalog_number:05d}"
    tens = catalog_number // 10_000
    rest = catalog_number % 10_000
    letter = _VALUE_TO_LETTER.get(tens)
    if letter is None:
        raise ValueError(f"No Alpha-5 letter for ten-thousands digit {tens}")
    return f"{letter}{rest:04d}"
