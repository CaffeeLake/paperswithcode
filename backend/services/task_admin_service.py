"""Idempotent task taxonomy creation for the maintenance CLI."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.database import Area, Task


@dataclass(frozen=True)
class TaskUpsertResult:
    id: int
    slug: str
    name: str
    status: str
    area: str
    parent_slug: str | None
    level: int

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "slug": self.slug,
            "name": self.name,
            "status": self.status,
            "area": self.area,
            "parent_slug": self.parent_slug,
            "level": self.level,
        }


def add_or_update_task(
    db: Session,
    *,
    slug: str,
    name: str,
    description: str,
    keywords: str,
    area_name: str,
    parent_reference: str | None = None,
    is_visible: bool = True,
) -> TaskUpsertResult:
    """Create or update one task and its optional parent relationship."""
    area = db.execute(select(Area).where(Area.name == area_name)).scalar_one_or_none()
    if area is None:
        raise ValueError(f"Area not found: {area_name}")

    parent = None
    if parent_reference:
        parent = db.execute(
            select(Task).where(Task.slug == parent_reference)
        ).scalar_one_or_none()
        if parent is None and parent_reference.isdigit():
            parent = db.get(Task, int(parent_reference))
        if parent is None:
            raise ValueError(f"Parent task not found: {parent_reference}")
        if parent.slug == slug:
            raise ValueError("A task cannot be its own parent")

    task = db.execute(select(Task).where(Task.slug == slug)).scalar_one_or_none()
    status = "updated" if task else "created"
    if task is None:
        task = Task(slug=slug, name=name)
        db.add(task)

    task.name = name
    task.description = description
    task.keywords = keywords
    task.area_id = area.id
    task.parent_id = parent.id if parent else None
    task.level = (parent.level + 1) if parent else 0
    task.is_visible = is_visible
    db.commit()

    return TaskUpsertResult(
        id=task.id,
        slug=slug,
        name=name,
        status=status,
        area=area.name,
        parent_slug=parent.slug if parent else None,
        level=task.level,
    )
