import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, inspect

from goodtohike.api.app import app, get_app
from goodtohike.elevation import (
    HybridFill,
    InterpolateOnly,
    LookUpEveryPoint,
    LookUpGaps,
)


def test_health_is_served_under_v1():
    response = TestClient(app).get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_is_not_served_without_the_version_prefix():
    response = TestClient(app).get("/health")

    assert response.status_code == 404


def test_get_app_publishes_title_and_version_in_openapi(engine: Engine):
    client = TestClient(get_app(title="Trail Test", version="9.8.7", engine=engine))

    info = client.get("/openapi.json").json()["info"]

    assert info["title"] == "Trail Test"
    assert info["version"] == "9.8.7"


def test_startup_creates_the_tables(app: FastAPI, engine: Engine):
    assert inspect(engine).get_table_names() == []

    with TestClient(app):
        assert inspect(engine).get_table_names() == ["routes", "water_reports"]


def test_elevation_is_looked_up_by_default(engine: Engine):
    built = get_app(title="GoodToHike", version="test", engine=engine)

    assert isinstance(built.state.elevation_filler, HybridFill)


@pytest.mark.parametrize(
    ("setting", "strategy"),
    [
        ("hybrid", HybridFill),
        ("interpolate", InterpolateOnly),
        ("lookup-gaps", LookUpGaps),
        ("lookup-every-point", LookUpEveryPoint),
    ],
)
def test_each_elevation_fill_setting_builds_its_strategy(
    engine: Engine, setting: str, strategy: type
):
    built = get_app(
        title="GoodToHike", version="test", engine=engine, elevation_fill=setting
    )

    assert isinstance(built.state.elevation_filler, strategy)


def test_unknown_elevation_fill_stops_the_app_being_built(engine: Engine):
    with pytest.raises(ValueError, match="'lookup-everything'"):
        get_app(
            title="GoodToHike",
            version="test",
            engine=engine,
            elevation_fill="lookup-everything",
        )
