"""Static file serving for the frontend in production."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.responses import Response

from habagou.config import settings

FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"


class FrontendStaticFiles(StaticFiles):
    """Static file server with SPA fallback for client-side routes."""

    async def get_response(self, path: str, scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404 or "." in Path(path).name:
                raise
            return await super().get_response("index.html", scope)


def mount_frontend(app: FastAPI) -> None:
    """Mount the frontend static files if the dist directory exists.

    In production, the frontend is built to `web/frontend/dist/` and served
    as static files. In development, the frontend dev server runs separately.
    """
    if not FRONTEND_DIST.is_dir():
        if settings.require_frontend:
            raise RuntimeError(f"frontend dist directory is missing: {FRONTEND_DIST}")
        return

    app.mount(
        "/",
        FrontendStaticFiles(directory=str(FRONTEND_DIST), html=True),
        name="frontend",
    )
