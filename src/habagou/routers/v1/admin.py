"""Admin API routes."""

import secrets
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import (  # noqa: TC002 - FastAPI resolves annotations.
    AsyncSession,
)

from habagou.config import settings
from habagou.db import get_session
from habagou.dtos.admin import PackAdminDTO, PackSortOrderPatchDTO
from habagou.events import Outcome, emit_workflow_event
from habagou.services.admin import AdminService

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.post(
    "/packs/{slug}/retire",
    response_model=PackAdminDTO,
    responses={
        401: {"description": "Missing or invalid admin token"},
        404: {"description": "Pack not found"},
        503: {"description": "Admin endpoints disabled"},
    },
)
async def retire_pack(
    slug: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    admin_token: Annotated[str | None, Header(alias="ADMIN_TOKEN")] = None,
) -> PackAdminDTO:
    started_at = time.perf_counter()
    _require_admin(token=admin_token, action="retire", slug=slug, started_at=started_at)
    result = await AdminService(session).retire_pack(slug)
    return _admin_result(result, action="retire", slug=slug, started_at=started_at)


@router.post(
    "/packs/{slug}/publish",
    response_model=PackAdminDTO,
    responses={
        401: {"description": "Missing or invalid admin token"},
        404: {"description": "Pack not found"},
        503: {"description": "Admin endpoints disabled"},
    },
)
async def publish_pack(
    slug: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    admin_token: Annotated[str | None, Header(alias="ADMIN_TOKEN")] = None,
) -> PackAdminDTO:
    started_at = time.perf_counter()
    _require_admin(
        token=admin_token, action="publish", slug=slug, started_at=started_at
    )
    result = await AdminService(session).publish_pack(slug)
    return _admin_result(result, action="publish", slug=slug, started_at=started_at)


@router.patch(
    "/packs/{slug}",
    response_model=PackAdminDTO,
    responses={
        401: {"description": "Missing or invalid admin token"},
        404: {"description": "Pack not found"},
        503: {"description": "Admin endpoints disabled"},
    },
)
async def patch_pack(
    slug: str,
    patch: PackSortOrderPatchDTO,
    session: Annotated[AsyncSession, Depends(get_session)],
    admin_token: Annotated[str | None, Header(alias="ADMIN_TOKEN")] = None,
) -> PackAdminDTO:
    started_at = time.perf_counter()
    _require_admin(
        token=admin_token,
        action="patch_sort_order",
        slug=slug,
        started_at=started_at,
    )
    result = await AdminService(session).set_pack_sort_order(slug, patch.sort_order)
    return _admin_result(
        result,
        action="patch_sort_order",
        slug=slug,
        started_at=started_at,
    )


def _require_admin(
    *,
    token: str | None,
    action: str,
    slug: str,
    started_at: float,
) -> None:
    if not settings.admin_token:
        _emit_admin_action(
            action=action,
            slug=slug,
            started_at=started_at,
            authorized=False,
            outcome="error",
            reason="disabled",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="admin endpoints disabled: ADMIN_TOKEN is unset",
        )

    if not secrets.compare_digest(token or "", settings.admin_token):
        _emit_admin_action(
            action=action,
            slug=slug,
            started_at=started_at,
            authorized=False,
            outcome="error",
            reason="unauthorized",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid admin token",
        )


def _admin_result(
    result: PackAdminDTO | None,
    *,
    action: str,
    slug: str,
    started_at: float,
) -> PackAdminDTO:
    if result is None:
        _emit_admin_action(
            action=action,
            slug=slug,
            started_at=started_at,
            authorized=True,
            outcome="error",
            reason="not_found",
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"pack not found: {slug}",
        )

    _emit_admin_action(
        action=action,
        slug=slug,
        started_at=started_at,
        authorized=True,
    )
    return result


def _emit_admin_action(
    *,
    action: str,
    slug: str,
    started_at: float,
    authorized: bool,
    outcome: Outcome = "ok",
    reason: str | None = None,
) -> None:
    fields: dict[str, object] = {
        "action": action,
        "pack_slug": slug,
        "authorized": authorized,
    }
    if reason is not None:
        fields["reason"] = reason
    emit_workflow_event(
        "admin_action",
        workflow="WF-09",
        outcome=outcome,
        duration_ms=_elapsed_ms(started_at),
        **fields,
    )


def _elapsed_ms(started_at: float) -> int:
    return round((time.perf_counter() - started_at) * 1000)
