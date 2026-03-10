"""Tests for dct.src.type_compat"""
import typing

import pytest

from dct.src.type_compat import is_compatible, normalize_type


def test_plain_int():
    assert normalize_type(int) == frozenset({"int"})


def test_plain_float():
    assert normalize_type(float) == frozenset({"float"})


def test_union_type():
    ann = int | float
    assert normalize_type(ann) == frozenset({"int", "float"})


def test_typing_union():
    ann = typing.Union[int, float]
    assert normalize_type(ann) == frozenset({"int", "float"})


def test_optional():
    ann = typing.Optional[int]
    assert normalize_type(ann) == frozenset({"int", "None"})


def test_unannotated_empty():
    import inspect
    assert normalize_type(inspect.Parameter.empty) == frozenset()


def test_none_annotation_empty():
    assert normalize_type(None) == frozenset()


def test_compatible_same():
    assert is_compatible(frozenset({"int"}), frozenset({"int"}))


def test_compatible_subset():
    assert is_compatible(frozenset({"int"}), frozenset({"int", "float"}))


def test_incompatible():
    assert not is_compatible(frozenset({"str"}), frozenset({"int", "float"}))


def test_empty_source_always_compatible():
    assert is_compatible(frozenset(), frozenset({"int"}))


def test_empty_target_always_compatible():
    assert is_compatible(frozenset({"int"}), frozenset())
