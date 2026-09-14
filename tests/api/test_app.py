from fastapi.testclient import TestClient

from goodtohike.api.app import app, get_app


def test_health_is_served_under_v1():
    response = TestClient(app).get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_is_not_served_without_the_version_prefix():
    response = TestClient(app).get("/health")

    assert response.status_code == 404


def test_get_app_publishes_title_and_version_in_openapi():
    client = TestClient(get_app(title="Trail Test", version="9.8.7"))

    info = client.get("/openapi.json").json()["info"]

    assert info["title"] == "Trail Test"
    assert info["version"] == "9.8.7"
