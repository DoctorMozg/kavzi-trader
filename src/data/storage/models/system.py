"""
System-related database models for SQLAlchemy.

This module defines SQLAlchemy models for system tables.
These models map to the database tables for storing system logs and configuration.
"""

from datetime import datetime
from typing import Any, Literal

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.data.storage.models.base import BaseModel


class SystemLogModel(BaseModel):
    """
    SQLAlchemy model for system_logs table.

    Stores system logs for monitoring and debugging.
    """

    __tablename__ = "system_logs"
    log_level: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        index=True,
    )  # DEBUG, INFO, WARNING, ERROR
    component: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        nullable=False,
    )

    # Constraints
    __table_args__ = (
        Index("ix_system_log_log_level_component", "log_level", "component"),
        Index("ix_system_log_created_at", "created_at"),
    )

    @classmethod
    def create_log(
        cls,
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        component: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> "SystemLogModel":
        """
        Create a system log entry.

        Args:
            log_level: Log level
            component: System component
            message: Log message
            details: Additional details as JSON

        Returns:
            SystemLogModel instance
        """
        return cls(
            log_level=log_level,
            component=component,
            message=message,
            details=details,
        )
