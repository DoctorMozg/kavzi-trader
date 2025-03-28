"""
DateTime schema for KavziTrader.

This module provides Pydantic schemas and utilities for handling datetime objects
with proper timezone information. This helps ensure consistent datetime handling
across the platform.
"""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from src.commons.time_utility import now_ts


class DateTimeWithTimezoneSchema(BaseModel):
    """Base schema for models requiring datetime fields with timezone information."""

    @field_validator("*", mode="before")
    @classmethod
    def ensure_timezone(cls, value: datetime | str | None) -> datetime | None:
        """
        Ensure that datetime fields have timezone information.

        Args:
            value: A datetime object, string, or None

        Returns:
            Datetime with timezone set to UTC if not already present, or None

        Raises:
            ValueError: If value is a string that cannot be parsed as a datetime
        """
        if value is None:
            return None

        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except ValueError as e:
                raise ValueError(f"Invalid datetime format: {value}") from e

        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=UTC)
            return value

        raise ValueError(f"Expected datetime or string, got {type(value)}")


class TimestampedSchema(DateTimeWithTimezoneSchema):
    """
    Mixin for models requiring created_at and updated_at fields.

    This schema provides standardized timestamp fields with proper timezone handling.
    """

    created_at: Annotated[datetime, Field(default_factory=now_ts)]
    updated_at: Annotated[datetime, Field(default_factory=now_ts)]
