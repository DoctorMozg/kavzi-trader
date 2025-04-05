"""
Base repository for database operations.

This module provides the base repository class with common database operations,
implementing the repository pattern to abstract database access.
"""

import logging
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Mapper

# Define a generic type for model classes
T = TypeVar("T")

logger = logging.getLogger(__name__)


class BaseRepository(Generic[T]):
    """
    Base repository class with common database operations.

    This class provides common CRUD operations for database entities.
    """

    def __init__(self, session: AsyncSession, model_class: type[T]) -> None:
        """
        Initialize a repository instance.

        Args:
            session: SQLAlchemy async session
            model_class: SQLAlchemy model class for this repository
        """
        self.session = session
        self.model_class = model_class
        self.mapper: Mapper = inspect(model_class)

        # Check if model has id attribute
        if not hasattr(model_class, "id"):
            logger.warning(
                f"Model class {model_class.__name__} does not have an 'id' attribute",
            )

    async def add(self, model: T) -> T:
        """
        Add a new entity to the database.

        Args:
            model: Model instance to add

        Returns:
            The added model instance
        """
        self.session.add(model)
        await self.session.flush()
        return model

    async def add_all(self, models: list[T]) -> list[T]:
        """
        Add multiple entities to the database.

        Args:
            models: List of model instances to add

        Returns:
            The list of added model instances
        """
        self.session.add_all(models)
        await self.session.flush()
        return models

    async def get_by_id(self, entity_id: int) -> T | None:
        """
        Get an entity by ID.

        Args:
            entity_id: Entity ID

        Returns:
            The entity if found, None otherwise
        """
        id_attr = getattr(self.model_class, "id", None)
        if id_attr is None:
            logger.error(f"Model {self.model_class.__name__} has no 'id' attribute")
            return None

        query = select(self.model_class).where(id_attr == entity_id)
        result = await self.session.execute(query)
        return result.scalars().first()  # type: ignore  # Entity will be of type T if found

    async def get_all(self) -> list[T]:
        """
        Get all entities.

        Returns:
            List of all entities
        """
        query = select(self.model_class)
        result = await self.session.execute(query)
        return list(result.scalars().all())  # type: ignore  # Entities will be of type list[T]

    async def update(self, model: T) -> T:
        """
        Update an entity in the database.

        Args:
            model: Model instance to update

        Returns:
            The updated model instance
        """
        self.session.add(model)
        await self.session.flush()
        return model

    async def delete(self, model: T) -> None:
        """
        Delete an entity from the database.

        Args:
            model: Model instance to delete
        """
        await self.session.delete(model)
        await self.session.flush()

    async def delete_by_id(self, entity_id: int) -> None:
        """
        Delete an entity by ID.

        Args:
            entity_id: Entity ID
        """
        entity = await self.get_by_id(entity_id)
        if entity:
            await self.delete(entity)
