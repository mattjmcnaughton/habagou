from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from habagou.web import serve

if TYPE_CHECKING:
    from pathlib import Path


def test_frontend_static_files_fall_back_to_index_for_spa_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    monkeypatch.setattr(serve, "FRONTEND_DIST", dist)

    app = FastAPI()
    serve.mount_frontend(app)

    response = TestClient(app).get("/packs/greetings/trace")

    assert response.status_code == 200
    assert '<div id="root"></div>' in response.text


def test_frontend_static_files_keep_missing_asset_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    monkeypatch.setattr(serve, "FRONTEND_DIST", dist)

    app = FastAPI()
    serve.mount_frontend(app)

    assert TestClient(app).get("/assets/missing.js").status_code == 404


def test_frontend_static_files_can_require_dist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(serve, "FRONTEND_DIST", tmp_path / "missing")
    monkeypatch.setattr(serve.settings, "require_frontend", True)

    with pytest.raises(RuntimeError, match="frontend dist directory is missing"):
        serve.mount_frontend(FastAPI())
