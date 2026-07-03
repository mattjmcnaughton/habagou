"""DTOs for admin API requests and responses."""

from __future__ import annotations

import uuid  # noqa: TC003 - Pydantic resolves UUID annotations at runtime.

from pydantic import BaseModel, Field

from habagou.models import PackStatus  # noqa: TC001 - Pydantic validation.


class PackAdminDTO(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    status: PackStatus
    sort_order: int


class PackSortOrderPatchDTO(BaseModel):
    sort_order: int = Field(ge=0)
