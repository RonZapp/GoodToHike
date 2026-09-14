from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from goodtohike.db import Base, RouteRecord, record_to_route, route_to_record
from goodtohike.route import Route


def test_route_survives_a_round_trip_through_the_database():
    route = Route(
        name="Hoh River",
        points=[(47.86, -123.93, 175.0), (47.87, -123.92, 180.5)],
        source="gpx",
    )
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        record = route_to_record(route)
        session.add(record)
        session.commit()
        record_id = record.id
        session.expunge_all()
        loaded = session.get(RouteRecord, record_id)

        assert loaded is not None
        assert record_to_route(loaded) == route
