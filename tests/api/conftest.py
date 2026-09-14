import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from goodtohike.api.app import get_app


@pytest.fixture
def app() -> FastAPI:
    # A fresh app per test, so a dependency override cannot leak into the next.
    return get_app(title="GoodToHike", version="test")


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)
