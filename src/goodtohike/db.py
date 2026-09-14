"""Database operations through SQLAlchemy."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Dialect, String, TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from goodtohike.geometry import get_cumulative_m
from goodtohike.route import MAX_NAME_LENGTH, Route


class UtcDateTime(TypeDecorator[datetime]):
    """A timestamp stored in UTC and always read back timezone-aware.
    
    SQLite has no timezone type, so SQLAlchemy returns its timestamps without
    one even when asked for ``timezone=True``. Everything is written in UTC,
    so attaching UTC on the way out is exact rather than a guess.
    """
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
            self, value: datetime | None, dialect: Dialect
        ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(UTC)

    def process_result_value(
            self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)

def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class RouteRecord(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(MAX_NAME_LENGTH))
    source: Mapped[str] = mapped_column(String(40))
    points: Mapped[list[list[float]]] = mapped_column(JSON)
    point_count: Mapped[int]
    length_m: Mapped[float]
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)


def route_to_record(route: Route) -> RouteRecord:
    """The stored from of a route, with its summary values worked out."""
    return RouteRecord(
        name=route.name,
        source=route.source,
        points=[[lat, lon, elevation] for lat, lon, elevation in route.points],
        point_count=len(route.points),
        length_m=get_cumulative_m(route.points)[-1],
    )


def record_to_route(record: RouteRecord) -> Route:
    """A route rebuilt from storage."""
    return Route(
        name=record.name,
        # JSON has no tuple type, so points come back as lists and are turned
        # into tuples here.
        points=[(lat, lon, elevation) for lat, lon, elevation in record.points],
        source=record.source,
    )
