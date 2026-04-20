"""Pure functions for decoding raw BLE characteristic bytes."""
from __future__ import annotations


_INT_WIDTHS = {1, 2, 4, 8}


def decode_bytes(raw: bytes) -> dict:
    """Return multiple decodings of a byte payload.

    Keys:
        hex: lowercase hex string, no prefix.
        utf8_or_none: UTF-8 decoded string, or None if invalid UTF-8 or empty.
        int_le_or_none: little-endian unsigned int when len in {1,2,4,8}; else None.
        length: byte length.
    """
    length = len(raw)
    hex_str = raw.hex()

    utf8: str | None
    if length == 0:
        utf8 = None
    else:
        try:
            utf8 = raw.decode("utf-8")
        except UnicodeDecodeError:
            utf8 = None

    int_le: int | None
    if length in _INT_WIDTHS:
        int_le = int.from_bytes(raw, "little", signed=False)
    else:
        int_le = None

    return {
        "hex": hex_str,
        "utf8_or_none": utf8,
        "int_le_or_none": int_le,
        "length": length,
    }
