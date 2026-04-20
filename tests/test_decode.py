from ble_mcp.decode import decode_bytes


def test_decode_empty():
    r = decode_bytes(b"")
    assert r == {"hex": "", "utf8_or_none": None, "int_le_or_none": None, "length": 0}


def test_decode_utf8_text():
    r = decode_bytes(b"hello")
    assert r["hex"] == "68656c6c6f"
    assert r["utf8_or_none"] == "hello"
    assert r["int_le_or_none"] is None  # 5 bytes is not a standard int width
    assert r["length"] == 5


def test_decode_uint8():
    r = decode_bytes(b"\x57")  # 87
    assert r["hex"] == "57"
    assert r["int_le_or_none"] == 87
    assert r["length"] == 1


def test_decode_uint16_le():
    r = decode_bytes(b"\x39\x30")  # 0x3039 = 12345
    assert r["hex"] == "3930"
    assert r["int_le_or_none"] == 12345
    assert r["length"] == 2


def test_decode_uint32_le():
    r = decode_bytes(b"\x01\x00\x00\x00")
    assert r["int_le_or_none"] == 1


def test_decode_non_utf8_bytes():
    r = decode_bytes(b"\xff\xfe\xfd")
    assert r["utf8_or_none"] is None
    assert r["hex"] == "fffefd"
