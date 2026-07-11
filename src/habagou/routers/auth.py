"""Authentication routes."""

from __future__ import annotations

from typing import Annotated

import structlog
from authlib.integrations.base_client.errors import OAuthError
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import (  # noqa: TC002 - FastAPI resolves annotations.
    AsyncSession,
)

from habagou.auth import PROVIDER_NAME, fetch_identity, oauth
from habagou.db import get_session
from habagou.dependencies import get_optional_current_user
from habagou.dtos.auth import SessionDTO, UserDTO
from habagou.events import workflow_event
from habagou.services.auth import AuthService

router = APIRouter(tags=["auth"])
logger = structlog.get_logger()


@router.get("/auth/login")
async def login(request: Request) -> Response:
    client = oauth.create_client(PROVIDER_NAME)
    if client is None:
        raise RuntimeError(f"auth provider is not registered: {PROVIDER_NAME}")
    callback_url = str(request.url_for("auth_callback"))
    return await client.authorize_redirect(request, callback_url)


@router.get("/auth/callback")
async def auth_callback(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    try:
        client = oauth.create_client(PROVIDER_NAME)
        if client is None:
            raise RuntimeError(f"auth provider is not registered: {PROVIDER_NAME}")
        token = await client.authorize_access_token(request)
        identity = fetch_identity(token)
        user = await AuthService(session).sign_in(identity)
    except (OAuthError, ValueError) as exc:
        logger.warning("auth_callback_failed", error=str(exc))
        return RedirectResponse(url="/login?error=auth_failed", status_code=303)

    request.session["user_id"] = str(user.id)
    async with workflow_event(
        "auth_signed_in",
        workflow="WF-AUTH-SIGN-IN",
        user_id=str(user.id),
        provider=PROVIDER_NAME,
    ):
        return RedirectResponse(url="/", status_code=303)


@router.post("/auth/logout", status_code=204)
async def logout(request: Request) -> Response:
    user_id = request.session.get("user_id")
    request.session.clear()
    async with workflow_event(
        "auth_signed_out",
        workflow="WF-AUTH-SIGN-OUT",
        user_id=str(user_id or ""),
        provider=PROVIDER_NAME,
    ):
        response = Response(status_code=204)
        response.delete_cookie("session", path="/")
        return response


@router.get("/api/v1/auth/session", response_model=SessionDTO)
async def get_auth_session(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SessionDTO:
    user = await get_optional_current_user(request, session)
    if user is None:
        return SessionDTO(authenticated=False, provider=PROVIDER_NAME)

    return SessionDTO(
        authenticated=True,
        provider=PROVIDER_NAME,
        user=UserDTO(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            email=user.email,
        ),
    )
