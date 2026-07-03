from __future__ import annotations

import pytest
from sqlalchemy import text

from habagou.db import async_session


@pytest.mark.anyio
async def test_database_connection() -> None:
    async with async_session() as session:
        result = await session.execute(text("SELECT 1"))

    assert result.scalar_one() == 1
