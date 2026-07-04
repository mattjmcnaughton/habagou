from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError

from habagou.app import create_app


class BrokenSession:
    async def __aenter__(self) -> None:
        raise SQLAlchemyError("database down")

    async def __aexit__(self, *args: object) -> None:
        return None


@pytest.mark.anyio
async def test_readyz_and_api_return_clean_errors_when_database_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("habagou.db.async_session", lambda: BrokenSession())
    transport = ASGITransport(app=create_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        ready = await client.get("/readyz", headers={"X-Request-ID": "ready-db-down"})
        packs = await client.get(
            "/api/v1/packs", headers={"X-Request-ID": "api-db-down"}
        )

    assert ready.status_code == 503
    assert ready.json() == {
        "error": {
            "code": "database_unavailable",
            "message": "database is unreachable",
            "request_id": "ready-db-down",
            "details": {"database": "unreachable"},
        }
    }
    assert packs.status_code == 503
    assert packs.json() == {
        "error": {
            "code": "database_unavailable",
            "message": "database is unavailable",
            "request_id": "api-db-down",
        }
    }
