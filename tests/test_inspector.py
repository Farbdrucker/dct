"""Tests for dct.src.inspector against the real transitions.py"""
from pathlib import Path

from dct.src.inspector import inspect_module, load_transitions_module, schema_version

TRANSITIONS_PATH = Path(__file__).parent.parent / "examples" / "transitions.py"


def _get_module():
    return load_transitions_module(TRANSITIONS_PATH)


def test_schema_version_is_string():
    v = schema_version(TRANSITIONS_PATH)
    assert v.startswith("sha256:")


def test_five_transitions():
    module = _get_module()
    schemas = inspect_module(module)
    names = {s.class_name for s in schemas}
    assert names == {"AddTwoInt", "AddTwoFloats", "Div", "Power", "Root"}


def test_power_config_field():
    module = _get_module()
    schemas = {s.class_name: s for s in inspect_module(module)}
    power = schemas["Power"]
    assert len(power.config_fields) == 1
    field = power.config_fields[0]
    assert field.name == "exponent"
    assert set(field.type_set) == {"int", "float"}
    assert field.required is True


def test_power_input_port():
    module = _get_module()
    schemas = {s.class_name: s for s in inspect_module(module)}
    power = schemas["Power"]
    assert len(power.input_ports) == 1
    port = power.input_ports[0]
    assert port.name == "base"
    assert set(port.type_set) == {"int", "float"}


def test_power_output_port():
    module = _get_module()
    schemas = {s.class_name: s for s in inspect_module(module)}
    power = schemas["Power"]
    assert power.output_port.name == "output"
    assert set(power.output_port.type_set) == {"float"}


def test_add_two_int_no_config():
    module = _get_module()
    schemas = {s.class_name: s for s in inspect_module(module)}
    node = schemas["AddTwoInt"]
    assert node.config_fields == []
    assert len(node.input_ports) == 2


def test_div_two_input_ports():
    module = _get_module()
    schemas = {s.class_name: s for s in inspect_module(module)}
    div = schemas["Div"]
    assert len(div.input_ports) == 2
    port_names = {p.name for p in div.input_ports}
    assert port_names == {"nominator", "denominator"}
