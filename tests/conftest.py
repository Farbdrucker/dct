from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dct.api.app import create_app

EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.fixture(scope="session")
def _app():
    return create_app(EXAMPLES / "transitions.py", EXAMPLES / "source.py")


@pytest.fixture(scope="module")
def client(_app):
    with TestClient(_app) as c:
        yield c
