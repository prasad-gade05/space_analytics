import pytest

from src.utils.alpha5 import ALPHA5_CEILING, alpha5_decode, alpha5_encode


def test_plain_numbers_roundtrip():
    for n in (0, 1, 4449, 99999):
        assert alpha5_decode(alpha5_encode(n)) == n
    assert alpha5_encode(25544) == "25544"
    assert alpha5_encode(99999) == "99999"


def test_alpha5_known_values():
    # A=10 -> 10xxxx; Z=33 -> 33xxxx = 339999 ceiling
    assert alpha5_decode("A0000") == 100_000
    assert alpha5_decode("A1234") == 101_234
    assert alpha5_decode("H9999") == 179_999   # A..H = 10..17
    assert alpha5_decode("J0000") == 180_000   # I skipped: J=18
    assert alpha5_decode("N9999") == 229_999   # J..N = 18..22
    assert alpha5_decode("P0000") == 230_000   # O skipped: P=23
    assert alpha5_decode("Z9999") == ALPHA5_CEILING == 339_999


def test_encode_decode_inverse():
    for n in (100_000, 100_403, 150_000, 239_999, 240_001, 339_999):
        assert alpha5_decode(alpha5_encode(n)) == n


def test_invalid_letters_rejected():
    with pytest.raises(ValueError, match="never used"):
        alpha5_decode("I1234")
    with pytest.raises(ValueError, match="never used"):
        alpha5_decode("O1234")
    with pytest.raises(ValueError):
        alpha5_decode("@1234")


def test_length_and_ceiling_enforced():
    with pytest.raises(ValueError):
        alpha5_decode("A123")
    with pytest.raises(ValueError):
        alpha5_decode("A12345")
    with pytest.raises(ValueError):
        alpha5_encode(340_000)
