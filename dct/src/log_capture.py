"""Streaming capture of print() / rich.print() / logging output as ANSI text."""
import io
import logging
import re
import sys
from contextlib import contextmanager
from typing import Callable

import rich
import rich.console
import rich.logging

# OSC escape sequences (e.g. Rich hyperlinks: ESC ] … ESC \ or BEL)
_OSC_RE = re.compile(r'\x1b\].*?(?:\x1b\\|\x07)')


class StreamingWriter(io.TextIOBase):
    def __init__(self, callback: Callable[[str], None]) -> None:
        super().__init__()
        self._callback = callback
        self._buf = ""

    def write(self, s: str) -> int:
        n = len(s)
        s = _OSC_RE.sub('', s)  # strip hyperlinks and other OSC sequences
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._callback(line)
        return n

    def flush(self) -> None:
        if self._buf:
            self._callback(self._buf)
            self._buf = ""

    @property
    def encoding(self) -> str:
        return "utf-8"

    def readable(self) -> bool:
        return False

    def writable(self) -> bool:
        return True


@contextmanager
def streaming_capture(callback: Callable[[str], None]):
    writer = StreamingWriter(callback)
    # Console for rich.print() — no highlight so markup colours pass through cleanly
    print_console = rich.console.Console(file=writer, force_terminal=True, width=120, highlight=False)
    # Console for logging — keep highlight so log values get coloured
    log_console = rich.console.Console(file=writer, force_terminal=True, width=120)

    original_stdout = sys.stdout
    original_rich_print = rich.print

    log_handler = rich.logging.RichHandler(
        console=log_console,
        show_path=False,   # no file:line hyperlinks
        markup=True,
    )

    # Swap out existing root handlers so we get one clean stream without duplicates.
    # (source.py installs a RichHandler on the root logger at import time.)
    existing_handlers = logging.root.handlers[:]
    for h in existing_handlers:
        logging.root.removeHandler(h)

    sys.stdout = writer
    rich.print = print_console.print
    logging.root.addHandler(log_handler)
    try:
        yield
    finally:
        writer.flush()
        sys.stdout = original_stdout
        rich.print = original_rich_print
        logging.root.removeHandler(log_handler)
        for h in existing_handlers:
            logging.root.addHandler(h)
