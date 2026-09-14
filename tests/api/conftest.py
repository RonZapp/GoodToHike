from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

from goodtohike.api.app import get_app


@pytest.fixture
def engine() -> Iterator[Engine]:
    # An in-memory database lives on one connection, and FastAPI runs handlers
    # on worker threads. StaticPool shares that one connection across threads,
    # so every request sees the same database.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    yield engine
    engine.dispose()


@pytest.fixture
def app(engine: Engine) -> FastAPI:
    # A fresh app per test, so a dependency override cannot leak into the next.
    return get_app(title="GoodToHike", version="test", engine=engine)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # Entering the client runs the app's startup, which creates the tables.
    with TestClient(app) as client:
        yield client
