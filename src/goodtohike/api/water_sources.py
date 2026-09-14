"""The /water-sources endpoints: field reports on whether water is running."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from goodtohike.api.routes import get_session
from goodtohike.db import WaterReportRecord
from goodtohike.water_reports import (
    ALLOWED_CLOCK_SKEW,
    MAX_NOTE_LENGTH,
    WATER_SOURCE_ID_PATTERN,
    WaterStatus,
)

router = APIRouter(tags=["water sources"])

# A list returns at most this many reports, newest first, until pagination
# exists. Older reports matter less for whether water is running today.
MAX_REPORTS_LISTED = 100

WaterSourceId = Annotated[
    str,
    Path(
        pattern=WATER_SOURCE_ID_PATTERN,
        description="The source's map id, such as an OpenStreetMap node.",
        examples=["osm-node-5207123456"],
    ),
]


class NewWaterReport(BaseModel):
    # A misspelt field is rejected rather than silently dropped.
    model_config = ConfigDict(extra="forbid")

    status: WaterStatus
    observed_at: AwareDatetime
    note: Annotated[str | None, Field(max_length=MAX_NOTE_LENGTH)] = None

    @field_validator("observed_at")
    @classmethod
    def check_not_in_future(cls, observed_at: datetime) -> datetime:
        if observed_at > datetime.now(UTC) + ALLOWED_CLOCK_SKEW:
            raise ValueError("must not be in the future")
        # Converted here, so the response to the POST shows the same UTC time
        # that every later read of the stored report does.
        return observed_at.astimezone(UTC)


class WaterReport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    water_source_id: str
    status: WaterStatus
    note: str | None
    observed_at: datetime
    received_at: datetime


class WaterReportList(BaseModel):
    # An object rather than a bare list, so a pagination cursor can be added
    # beside the reports without breaking clients.
    reports: list[WaterReport]


@router.post("/water-sources/{water_source_id}/reports", status_code=201)
def create_water_report(
    request: Request,
    response: Response,
    water_source_id: WaterSourceId,
    report: NewWaterReport,
    session: Annotated[Session, Depends(get_session)],
) -> WaterReport:
    record = WaterReportRecord(
        water_source_id=water_source_id,
        status=report.status,
        note=report.note,
        observed_at=report.observed_at,
    )
    session.add(record)
    session.commit()

    response.headers["Location"] = str(
        request.url_for(
            "get_water_report", water_source_id=water_source_id, report_id=record.id
        )
    )
    return WaterReport.model_validate(record)


@router.get("/water-sources/{water_source_id}/reports")
def list_water_reports(
    water_source_id: WaterSourceId,
    session: Annotated[Session, Depends(get_session)],
) -> WaterReportList:
    """Reports on a water source, most recently observed first.

    A source nobody has reported on has an empty list rather than a 404, since
    nothing here knows which water sources exist.
    """
    query = (
        select(WaterReportRecord)
        .where(WaterReportRecord.water_source_id == water_source_id)
        .order_by(WaterReportRecord.observed_at.desc(), WaterReportRecord.id.desc())
        .limit(MAX_REPORTS_LISTED)
    )
    return WaterReportList(
        reports=[
            WaterReport.model_validate(record) for record in session.scalars(query)
        ]
    )


@router.get("/water-sources/{water_source_id}/reports/{report_id}")
def get_water_report(
    water_source_id: WaterSourceId,
    report_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> WaterReport:
    record = session.get(WaterReportRecord, report_id)
    # A report asked for under a different source is as missing as one that
    # never existed.
    if record is None or record.water_source_id != water_source_id:
        raise HTTPException(
            status_code=404,
            detail=f"Water source {water_source_id} has no report {report_id}.",
        )
    return WaterReport.model_validate(record)
