from __future__ import annotations
import dataclasses
import json
import threading
from typing import Any


@dataclasses.dataclass
class _Entry:
    key_lock: threading.Lock
    instance: Any
    ready: bool


class InstanceCache:
    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], _Entry] = {}
        self._lock = threading.Lock()

    def get_or_create(self, class_name: str, cls: type, config: dict[str, Any]) -> Any:
        key = (class_name, json.dumps(config, sort_keys=True))
        # Phase 1: get or register entry
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                entry = _Entry(key_lock=threading.Lock(), instance=None, ready=False)
                self._entries[key] = entry
            elif entry.ready:
                return entry.instance  # fast path
        # Phase 2: initialize under per-entry lock (double-checked)
        with entry.key_lock:
            if not entry.ready:
                entry.instance = cls(**config)
                entry.ready = True
        return entry.instance

    def clear(self) -> None:
        with self._lock:
            self._entries = {}
