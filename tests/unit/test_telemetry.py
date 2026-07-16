"""Unit tests for optional Logfire telemetry configuration."""

from unittest.mock import Mock

import pytest
from fastapi import FastAPI

import habagou.telemetry as telemetry


def test_logfire_is_token_optional_and_excludes_system_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure = Mock()
    instrument_sqlalchemy = Mock()
    instrument_pydantic_ai = Mock()
    instrument_system_metrics = Mock()

    monkeypatch.setattr(telemetry, "_logfire_configured", False)
    monkeypatch.setattr(telemetry.settings, "logfire_token", "")
    monkeypatch.setattr(telemetry.settings, "otel_exporter_otlp_endpoint", "")
    monkeypatch.setattr(telemetry.logfire, "configure", configure)
    monkeypatch.setattr(
        telemetry.logfire, "instrument_sqlalchemy", instrument_sqlalchemy
    )
    monkeypatch.setattr(
        telemetry.logfire, "instrument_pydantic_ai", instrument_pydantic_ai
    )
    monkeypatch.setattr(
        telemetry.logfire, "instrument_system_metrics", instrument_system_metrics
    )

    telemetry._configure_logfire()

    configure.assert_called_once_with(
        send_to_logfire="if-token-present",
        token=None,
        service_name="habagou",
        console=False,
        additional_span_processors=[],
    )
    instrument_sqlalchemy.assert_called_once_with(telemetry.db.engine)
    instrument_pydantic_ai.assert_called_once_with(include_content=True)
    instrument_system_metrics.assert_not_called()


def test_logfire_configuration_is_process_wide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure = Mock()
    instrument_sqlalchemy = Mock()
    instrument_pydantic_ai = Mock()

    monkeypatch.setattr(telemetry, "_logfire_configured", False)
    monkeypatch.setattr(telemetry.settings, "logfire_token", "test-token")
    monkeypatch.setattr(telemetry.settings, "otel_exporter_otlp_endpoint", "")
    monkeypatch.setattr(telemetry.logfire, "configure", configure)
    monkeypatch.setattr(
        telemetry.logfire, "instrument_sqlalchemy", instrument_sqlalchemy
    )
    monkeypatch.setattr(
        telemetry.logfire, "instrument_pydantic_ai", instrument_pydantic_ai
    )

    telemetry._configure_logfire()
    telemetry._configure_logfire()

    assert configure.call_count == 1
    assert configure.call_args.kwargs["token"] == "test-token"
    assert instrument_sqlalchemy.call_count == 1
    assert instrument_pydantic_ai.call_count == 1


def test_setup_telemetry_instruments_each_fastapi_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_logfire = Mock()
    instrument_fastapi = Mock()
    first_app = FastAPI()
    second_app = FastAPI()

    monkeypatch.setattr(telemetry, "_configure_logfire", configure_logfire)
    monkeypatch.setattr(telemetry.logfire, "instrument_fastapi", instrument_fastapi)

    telemetry.setup_telemetry(first_app)
    telemetry.setup_telemetry(second_app)

    assert configure_logfire.call_count == 2
    assert instrument_fastapi.call_args_list == [
        ((first_app,), {}),
        ((second_app,), {}),
    ]
