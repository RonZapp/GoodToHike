from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response

from goodtohike.api.water_sources import MAX_REPORTS_LISTED
from goodtohike.water_reports import MAX_NOTE_LENGTH

SPRING = "osm-node-5207123456"
OTHER_SPRING = "osm-node-42"

# Written out rather than imported, so a typo in the source cannot also be
# the thing the test expects.
PROBLEM_CONTENT_TYPE = "application/problem+json"


def hours_ago(hours: float) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat()


def report(client: TestClient, source: str = SPRING, **overrides: object) -> Response:
    body = {"status": "flowing", "observed_at": hours_ago(1), **overrides}
    return client.post(f"/v1/water-sources/{source}/reports", json=body)


def assert_invalid_request(response: Response, mentioning: str) -> None:
    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_CONTENT_TYPE
    assert mentioning in response.json()["detail"]


# Creating


def test_report_returns_201_with_the_report(client: TestClient):
    response = report(client, status="trickle", note="Barely enough to filter.")

    assert response.status_code == 201
    body = response.json()
    assert body["water_source_id"] == SPRING
    assert body["status"] == "trickle"
    assert body["note"] == "Barely enough to filter."


def test_report_can_be_fetched_from_its_location(client: TestClient):
    # An offset other than UTC, so the stored and echoed forms must agree.
    created = report(client, observed_at="2026-09-13T08:30:00-07:00")

    fetched = client.get(created.headers["location"])

    assert fetched.status_code == 200
    assert fetched.json() == created.json()


def test_note_is_optional(client: TestClient):
    response = report(client)

    assert response.status_code == 201
    assert response.json()["note"] is None


def test_observed_at_keeps_its_instant_and_comes_back_in_utc(client: TestClient):
    response = report(client, observed_at="2026-09-13T08:30:00-07:00")

    observed_at = datetime.fromisoformat(response.json()["observed_at"])
    assert observed_at == datetime(2026, 9, 13, 15, 30, tzinfo=UTC)
    assert observed_at.utcoffset() == timedelta(0)


def test_received_at_is_set_by_the_server(client: TestClient):
    before = datetime.now(UTC)

    body = report(client, observed_at=hours_ago(48)).json()

    received_at = datetime.fromisoformat(body["received_at"])
    assert before - timedelta(seconds=1) <= received_at <= datetime.now(UTC)


@pytest.mark.parametrize(
    "source", ["osm-way-123", "osm-relation-9876543210", "osm-node-1"]
)
def test_every_kind_of_map_element_is_a_water_source(client: TestClient, source):
    assert report(client, source=source).status_code == 201


# Rejecting


@pytest.mark.parametrize("status", ["running", "Flowing", "", None])
def test_unknown_status_is_rejected(client: TestClient, status):
    assert_invalid_request(report(client, status=status), "status")


def test_missing_observed_at_is_rejected(client: TestClient):
    response = client.post(
        f"/v1/water-sources/{SPRING}/reports", json={"status": "dry"}
    )

    assert_invalid_request(response, "observed_at")


def test_observed_at_without_a_timezone_is_rejected(client: TestClient):
    assert_invalid_request(
        report(client, observed_at="2026-09-13T08:30:00"), "observed_at"
    )


def test_observed_at_in_the_future_is_rejected(client: TestClient):
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).isoformat()

    assert_invalid_request(report(client, observed_at=tomorrow), "observed_at")


def test_observed_at_a_moment_ahead_is_allowed_for_clock_skew(client: TestClient):
    a_minute_ahead = (datetime.now(UTC) + timedelta(minutes=1)).isoformat()

    assert report(client, observed_at=a_minute_ahead).status_code == 201


def test_note_longer_than_the_limit_is_rejected(client: TestClient):
    assert_invalid_request(report(client, note="x" * (MAX_NOTE_LENGTH + 1)), "note")


def test_unknown_field_is_rejected(client: TestClient):
    # A typo here would otherwise be dropped, and the report saved without it.
    assert_invalid_request(report(client, obseved_at=hours_ago(2)), "obseved_at")


def test_client_cannot_set_received_at(client: TestClient):
    assert_invalid_request(report(client, received_at=hours_ago(2)), "received_at")


@pytest.mark.parametrize(
    "source",
    ["5207123456", "osm-node-", "osm-node-0123", "osm-point-1", "OSM-NODE-1"],
)
def test_malformed_water_source_id_is_rejected(client: TestClient, source):
    assert_invalid_request(report(client, source=source), "water_source_id")


# Listing


def test_source_with_no_reports_has_an_empty_list(client: TestClient):
    response = client.get(f"/v1/water-sources/{SPRING}/reports")

    assert response.status_code == 200
    assert response.json() == {"reports": []}


def test_list_is_newest_observation_first_not_newest_received(client: TestClient):
    # Sent in an order that differs from when each was seen.
    report(client, status="flowing", observed_at=hours_ago(30))
    report(client, status="dry", observed_at=hours_ago(2))
    report(client, status="trickle", observed_at=hours_ago(10))

    body = client.get(f"/v1/water-sources/{SPRING}/reports").json()

    assert [r["status"] for r in body["reports"]] == ["dry", "trickle", "flowing"]


def test_list_holds_only_that_sources_reports(client: TestClient):
    report(client, source=SPRING)
    report(client, source=OTHER_SPRING)

    body = client.get(f"/v1/water-sources/{SPRING}/reports").json()

    assert {r["water_source_id"] for r in body["reports"]} == {SPRING}


def test_list_is_capped_to_the_most_recent(client: TestClient):
    for hours in range(MAX_REPORTS_LISTED + 1):
        report(client, observed_at=hours_ago(hours + 1))

    reports = client.get(f"/v1/water-sources/{SPRING}/reports").json()["reports"]

    assert len(reports) == MAX_REPORTS_LISTED
    # The oldest, observed MAX_REPORTS_LISTED + 1 hours ago, is the one left out.
    oldest_listed = datetime.fromisoformat(reports[-1]["observed_at"])
    assert datetime.now(UTC) - oldest_listed < timedelta(hours=MAX_REPORTS_LISTED + 1)


def test_list_with_malformed_source_id_is_rejected(client: TestClient):
    assert_invalid_request(
        client.get("/v1/water-sources/spring/reports"), "water_source_id"
    )


# Fetching one


def test_unknown_report_is_a_404_problem(client: TestClient):
    response = client.get(f"/v1/water-sources/{SPRING}/reports/999")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_CONTENT_TYPE


def test_report_under_a_different_source_is_a_404_problem(client: TestClient):
    report_id = report(client, source=SPRING).json()["id"]

    response = client.get(f"/v1/water-sources/{OTHER_SPRING}/reports/{report_id}")

    assert response.status_code == 404
