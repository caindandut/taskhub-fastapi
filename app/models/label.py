from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import (
    DEFAULT_LABEL_COLOR,
    LABEL_COLOR_LENGTH,
    LABEL_NAME_MAX_LENGTH,
)
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.task import Task


class Label(Base):
    __tablename__ = "labels"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(LABEL_NAME_MAX_LENGTH))
    color: Mapped[str] = mapped_column(
        String(LABEL_COLOR_LENGTH), server_default=DEFAULT_LABEL_COLOR
    )

    project: Mapped[Project] = relationship(back_populates="labels", lazy="raise")
    tasks: Mapped[list[Task]] = relationship(
        secondary="task_labels",
        back_populates="labels",
        passive_deletes=True,
        lazy="raise",
    )
