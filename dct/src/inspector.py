"""Inspect the transitions and sources modules and produce NodeSchema objects."""
from __future__ import annotations

import dataclasses
import hashlib
import importlib
import inspect
import typing
from pathlib import Path
from types import ModuleType

import pydantic
import pydantic.dataclasses
from pydantic import TypeAdapter

from dct.api.models import ConfigField, NodeSchema, Port
from dct.src.type_compat import normalize_type


def _type_label(annotation: object) -> str:
    """Return a human-readable type string."""
    if annotation is inspect.Parameter.empty:
        return "any"
    return str(annotation).replace("typing.", "").replace("<class '", "").replace("'>", "")


def _config_fields_for(cls: type) -> list[ConfigField]:
    """Extract config fields from a Pydantic dataclass."""
    fields = []
    for field in dataclasses.fields(cls):
        raw_ann = cls.__dataclass_fields__[field.name].type if hasattr(cls, "__dataclass_fields__") else field.type
        type_set = normalize_type(raw_ann)
        has_default = (
            not isinstance(field.default, dataclasses._MISSING_TYPE)  # type: ignore[attr-defined]
            or not isinstance(field.default_factory, dataclasses._MISSING_TYPE)  # type: ignore[attr-defined]
        )
        default_val = None
        if not isinstance(field.default, dataclasses._MISSING_TYPE):  # type: ignore[attr-defined]
            default_val = field.default
        fields.append(ConfigField(
            name=field.name,
            type=_type_label(raw_ann),
            type_set=sorted(type_set),
            default=default_val,
            required=not has_default,
            json_schema=_json_schema_for(raw_ann),
        ))
    return fields


def _json_schema_for(annotation: object) -> dict:
    """Generate a JSON schema dict for a field type annotation."""
    try:
        return TypeAdapter(annotation).json_schema()
    except Exception:
        return {"type": "string"}


def inspect_module(module: ModuleType) -> list[NodeSchema]:
    """Return a NodeSchema for every Pydantic dataclass with __call__ in *module*."""
    schemas: list[NodeSchema] = []

    for name, cls in inspect.getmembers(module, inspect.isclass):
        if not pydantic.dataclasses.is_pydantic_dataclass(cls):
            continue
        if cls.__module__ != module.__name__:
            continue
        if "__call__" not in cls.__dict__:
            continue  # skip base classes or non-callables

        sig = inspect.signature(cls.__call__)
        input_ports: list[Port] = []
        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
            ann = param.annotation
            type_set = normalize_type(ann)
            input_ports.append(Port(name=param_name, type=_type_label(ann), type_set=sorted(type_set)))

        ret = sig.return_annotation
        out_type_set = normalize_type(ret)
        output_port = Port(name="output", type=_type_label(ret), type_set=sorted(out_type_set))

        schemas.append(NodeSchema(
            class_name=name,
            kind="transition",
            description=inspect.getdoc(cls),
            config_fields=_config_fields_for(cls),
            input_ports=input_ports,
            output_port=output_port,
        ))

    return schemas


def inspect_sources_module(module: ModuleType) -> list[NodeSchema]:
    """Return a NodeSchema for every Pydantic dataclass with __iter__ in *module*."""
    schemas: list[NodeSchema] = []

    for name, cls in inspect.getmembers(module, inspect.isclass):
        if not pydantic.dataclasses.is_pydantic_dataclass(cls):
            continue
        if cls.__module__ != module.__name__:
            continue
        if "__iter__" not in cls.__dict__:
            continue  # skip Source base or non-sources

        # Output type: extract T from Iterator[T] return annotation of __iter__
        try:
            hints = typing.get_type_hints(cls.__iter__)
            iter_return = hints.get("return", inspect.Parameter.empty)
            type_args = typing.get_args(iter_return)
            out_ann = type_args[0] if type_args else inspect.Parameter.empty
        except Exception:
            out_ann = inspect.Parameter.empty

        out_type_set = normalize_type(out_ann)
        output_port = Port(name="output", type=_type_label(out_ann), type_set=sorted(out_type_set))

        schemas.append(NodeSchema(
            class_name=name,
            kind="source",
            description=inspect.getdoc(cls),
            config_fields=_config_fields_for(cls),
            input_ports=[],
            output_port=output_port,
        ))

    return schemas


def schema_version(transitions_path: Path) -> str:
    """Return sha256 hex digest of the transitions file."""
    return "sha256:" + hashlib.sha256(transitions_path.read_bytes()).hexdigest()[:16]


def _spec_name(path: Path) -> str:
    """Return a unique sys.modules key for a user-supplied file path."""
    return f"_dct_user_{path.stem}_{hash(str(path.resolve())) & 0xFFFFFF:06x}"


def _load_module_from_path(spec_name: str, path: Path) -> ModuleType:
    """Load or reload a module from a file path into sys.modules[spec_name]."""
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(spec_name, path)
    if spec_name in sys.modules:
        module = sys.modules[spec_name]
    else:
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        sys.modules[spec_name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def load_source_module(source_path: Path) -> ModuleType:
    """Import (or reload) the source module from *source_path*."""
    return _load_module_from_path(_spec_name(source_path), source_path)


def load_transitions_module(transitions_path: Path) -> ModuleType:
    """Import (or reload) the transitions module from *transitions_path*."""
    return _load_module_from_path(_spec_name(transitions_path), transitions_path)
