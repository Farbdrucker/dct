"""Schema cache with hot-reload via watchfiles."""

from __future__ import annotations

import threading
from pathlib import Path

from dct.api.models import NodeSchema
from dct.src.inspector import (
    inspect_module,
    inspect_sources_module,
    load_source_module,
    load_transitions_module,
    schema_version,
)
from dct.src.instance_cache import InstanceCache

ClassRegistry = dict[str, type]


class SchemaCache:
    def __init__(self) -> None:
        self._schemas: list[NodeSchema] = []
        self._version: str = ""
        self._class_registry: ClassRegistry = {}
        self._instance_cache = InstanceCache()
        self._lock = threading.Lock()

    def refresh(self, transitions_path: Path, source_path: Path | None = None) -> None:
        t_module = load_transitions_module(transitions_path)
        schemas = inspect_module(t_module)

        registry: ClassRegistry = {}
        for schema in schemas:
            cls = getattr(t_module, schema.class_name, None)
            if cls is not None:
                registry[schema.class_name] = cls

        if source_path is not None:
            s_module = load_source_module(source_path)
            source_schemas = inspect_sources_module(s_module)
            schemas = schemas + source_schemas
            for schema in source_schemas:
                cls = getattr(s_module, schema.class_name, None)
                if cls is not None:
                    registry[schema.class_name] = cls

        version = schema_version(transitions_path)

        with self._lock:
            self._schemas = schemas
            self._version = version
            self._class_registry = registry
            self._instance_cache.clear()

    def get(self) -> tuple[list[NodeSchema], str, ClassRegistry, InstanceCache]:
        with self._lock:
            return (
                self._schemas,
                self._version,
                self._class_registry,
                self._instance_cache,
            )


async def watch_transitions(
    transitions_path: Path, source_path: Path | None, cache: SchemaCache
) -> None:
    """Background coroutine: watch source files and refresh cache on change."""
    from watchfiles import awatch

    watch_paths = [transitions_path]
    if source_path is not None:
        watch_paths.append(source_path)

    async for _ in awatch(*watch_paths):
        try:
            cache.refresh(transitions_path, source_path)
        except Exception as exc:
            import logging

            logging.getLogger(__name__).error("Failed to reload: %s", exc)
