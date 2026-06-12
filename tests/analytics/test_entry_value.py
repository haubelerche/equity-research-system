from __future__ import annotations
import pytest
from backend.analytics._entry import entry_value


class _Fact:
    def __init__(self, value): self.value = value


def test_unwraps_fact_entry():
    assert entry_value(_Fact(12.5)) == 12.5

def test_plain_number_passes_through():
    assert entry_value(7) == 7.0
    assert entry_value("3.14") == 3.14

def test_dict_with_value_key_is_unwrapped():
    assert entry_value({"value": 99, "unit": "VND bn"}) == 99.0

def test_none_returns_none():
    assert entry_value(None) is None

def test_unconvertible_dict_raises_clear_error():
    with pytest.raises(TypeError) as exc:
        entry_value({"unit": "VND bn"})
    assert "entry_value" in str(exc.value)


def test_comma_string_is_parsed():
    assert entry_value("1,234.56") == 1234.56


def test_bool_is_refused():
    with pytest.raises(TypeError):
        entry_value(True)


def test_dict_amount_and_val_keys():
    assert entry_value({"amount": 5}) == 5.0
    assert entry_value({"val": 6}) == 6.0


def test_dict_value_none_returns_none():
    assert entry_value({"value": None, "unit": "VND bn"}) is None


def test_deep_recursion_is_bounded():
    class _Loop:
        @property
        def value(self): return self
    with pytest.raises(TypeError):
        entry_value(_Loop())
