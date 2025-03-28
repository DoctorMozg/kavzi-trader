"""
System-related database models for SQLAlchemy.

This module defines SQLAlchemy models for system tables.
These models map to the database tables for storing system logs and configuration.
"""

from typing import Any, Literal, cast

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

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


class SystemConfigModel(BaseModel):
    """
    SQLAlchemy model for system_config table.

    Stores system configuration settings.
    """

    __tablename__ = "system_config"
    key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
    )
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_editable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    @classmethod
    def get_value(
        cls,
        session: Session,
        key: str,
        default: str | None = None,
    ) -> str | None:
        """
        Get a configuration value.

        Args:
            session: SQLAlchemy session
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        config = session.query(cls).filter(cls.key == key).first()
        if config:
            return cast(str, config.value)
        return default

    @classmethod
    def set_value(
        cls,
        session: Session,
        key: str,
        value: str,
        description: str | None = None,
        is_editable: bool = True,
    ) -> "SystemConfigModel":
        """
        Set a configuration value.

        Args:
            session: SQLAlchemy session
            key: Configuration key
            value: Configuration value
            description: Optional description
            is_editable: Whether the config is user-editable

        Returns:
            SystemConfigModel instance
        """
        config = session.query(cls).filter(cls.key == key).first()
        if config:
            # Update existing config
            config.value = value
            if description:
                config.description = description
            config.is_editable = is_editable
        else:
            # Create new config
            config = cls(
                key=key,
                value=value,
                description=description,
                is_editable=is_editable,
            )
            session.add(config)

        return cast("SystemConfigModel", config)
