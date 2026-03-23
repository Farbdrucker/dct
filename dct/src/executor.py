# Backward-compat shim — use dct.engine.executor instead.
from dct.engine.executor import *  # noqa: F401, F403
from dct.engine.executor import (  # noqa: F401
    ClassRegistry,
    _build_failure_report,
    _build_graph,
    _execute_row,
    _topo_sort,
)
