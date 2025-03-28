"""
Base models for database tables.

This module defines base classes for SQLAlchemy models with common
fields and functionality shared across all database models.
"""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Mapped, mapped_column

from src.commons.time_utility import now_ts
from src.data.storage.database import Base


class BaseModel(Base):
    """
    Base class for all SQLAlchemy models.

    Provides common fields and functionality:
    - id: Primary key
    - created_at: Timestamp for when the record was created
    - updated_at: Timestamp for when the record was last updated

    This class is abstract and should not be instantiated directly.
    """

    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=now_ts)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=now_ts,
        onupdate=now_ts,
    )

    def to_dict(self) -> dict[str, Any]:
        """
        Convert model to dictionary.

        Returns:
            Dictionary with column name -> value mapping
        """
        return {
            column.name: getattr(self, column.name) for column in self.__table__.columns
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BaseModel":
        """
        Create model instance from dictionary.

        Args:
            data: Dictionary with column name -> value mapping

        Returns:
            Model instance
        """
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})

    def __repr__(self) -> str:
        """String representation of the model."""
        values = ", ".join(
            f"{column.name}={getattr(self, column.name)!r}"
            for column in self.__table__.columns
            if column.name in ["id", "name"]
            or (hasattr(self, "symbol") and column.name == "symbol")
        )
        return f"{self.__class__.__name__}({values})"
