"""Admin feature-flag API routes.

Flags are defined in code (``habagou.services.feature_flags``); these
endpoints manage the per-user database overrides. The whole surface is
admin-only: regular users receive their resolved flag map on the auth session
probe and never talk to these routes.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import (  # noqa: TC002 - FastAPI resolves annotations.
    AsyncSession,
)

from habagou.authz import is_admin
from habagou.db import get_session
from habagou.dependencies import get_current_user
from habagou.dtos.feature_flags import (
    FeatureFlagListDTO,
    FeatureFlagOverrideDTO,
    FeatureFlagOverrideSetDTO,
)
from habagou.events import workflow_event
from habagou.models import User  # noqa: TC001 - FastAPI resolves annotations.
from habagou.services.feature_flags import FeatureFlagService, known_flag_keys

router = APIRouter(prefix="/api/v1/admin/feature-flags", tags=["feature-flags"])


async def require_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="feature-flag management requires an admin account",
        )
    return current_user


@router.get("", response_model=FeatureFlagListDTO)
async def list_feature_flags(
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin: Annotated[User, Depends(require_admin)],
) -> FeatureFlagListDTO:
    return FeatureFlagListDTO(flags=await FeatureFlagService(session).list_flags())


@router.put(
    "/{flag_key}/users/{user_id}",
    response_model=FeatureFlagOverrideDTO,
    responses={404: {"description": "Unknown flag or user"}},
)
async def set_feature_flag_override(
    flag_key: str,
    user_id: uuid.UUID,
    override: FeatureFlagOverrideSetDTO,
    session: Annotated[AsyncSession, Depends(get_session)],
    admin: Annotated[User, Depends(require_admin)],
) -> FeatureFlagOverrideDTO:
    _ensure_known_flag(flag_key)
    async with workflow_event(
        "feature_flag_override_set",
        workflow="WF-ADMIN-FLAGS",
        flag_key=flag_key,
        target_user_id=str(user_id),
        enabled=override.enabled,
        admin_user_id=str(admin.id),
    ) as event:
        updated = await FeatureFlagService(session).set_user_override(
            flag_key=flag_key, user_id=user_id, enabled=override.enabled
        )
        if not updated:
            event.outcome = "error"
            event.fields["reason"] = "user_not_found"
            raise _user_not_found(user_id)
        return FeatureFlagOverrideDTO(
            flag_key=flag_key, user_id=user_id, enabled=override.enabled
        )


@router.delete(
    "/{flag_key}/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "Unknown flag"}},
)
async def clear_feature_flag_override(
    flag_key: str,
    user_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    admin: Annotated[User, Depends(require_admin)],
) -> None:
    _ensure_known_flag(flag_key)
    async with workflow_event(
        "feature_flag_override_cleared",
        workflow="WF-ADMIN-FLAGS",
        flag_key=flag_key,
        target_user_id=str(user_id),
        admin_user_id=str(admin.id),
    ) as event:
        deleted = await FeatureFlagService(session).clear_user_override(
            flag_key=flag_key, user_id=user_id
        )
        # Idempotent: clearing an absent override is a no-op 204, not a 404.
        event.fields["deleted"] = deleted


def _ensure_known_flag(flag_key: str) -> None:
    if flag_key not in known_flag_keys():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown feature flag: {flag_key}",
        )


def _user_not_found(user_id: uuid.UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"user not found: {user_id}",
    )
