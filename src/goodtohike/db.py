"""Database operations through SQLAlchemy."""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Dialect, String, TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from goodtohike.geometry import get_cumulative_m
from goodtohike.route import MAX_NAME_LENGTH, Route
from goodtohike.water_reports import MAX_NOTE_LENGTH, MAX_WATER_SOURCE_ID_LENGTH


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
    # deferred tells SQLAlchemy to not load this column when loading a record,
    # it will only load our relatively large JSON when coe actually reads
    # record.points
    points: Mapped[list[list[float]]] = mapped_column(JSON, deferred=True)
    point_count: Mapped[int]
    length_m: Mapped[float]
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)


class WaterReportRecord(Base):
    __tablename__ = "water_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Indexed, because every read looks reports up by their water source.
    water_source_id: Mapped[str] = mapped_column(
        String(MAX_WATER_SOURCE_ID_LENGTH), index=True
    )
    status: Mapped[str] = mapped_column(String(10))
    note: Mapped[str | None] = mapped_column(String(MAX_NOTE_LENGTH))
    # When the reporter saw the water, which can be days before they regained
    # signal and sent the report.
    observed_at: Mapped[datetime] = mapped_column(UtcDateTime)
    received_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)


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
