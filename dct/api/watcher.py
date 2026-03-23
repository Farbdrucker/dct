# Backward-compat shim — use dct.server.watcher instead.
from dct.server.watcher import *  # noqa: F401, F403
from dct.server.watcher import SchemaCache, watch_transitions  # noqa: F401
