"""OpenTelemetry and Logfire setup."""

import logfire
from fastapi import FastAPI
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from habagou import db
from habagou.config import settings

_logfire_configured = False


def setup_telemetry(app: FastAPI) -> None:
    """Configure process-wide telemetry and instrument this FastAPI app."""
    _configure_logfire()
    logfire.instrument_fastapi(app)


def _configure_logfire() -> None:
    """Configure Logfire and Pydantic AI instrumentation once per process."""
    global _logfire_configured  # noqa: PLW0603 - process-wide SDK configuration
    if _logfire_configured:
        return

    span_processors = []
    if settings.otel_exporter_otlp_endpoint:
        exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
        span_processors.append(BatchSpanProcessor(exporter))

    logfire.configure(
        send_to_logfire="if-token-present",
        token=settings.logfire_token or None,
        service_name="habagou",
        console=False,
        additional_span_processors=span_processors,
    )
    # Instrument the already-created engine and future SQLAlchemy engines.
    logfire.instrument_sqlalchemy(db.engine)
    # Conversation content is intentionally retained for reviewing generation
    # quality in Logfire, including replayed history, tool calls, and responses.
    logfire.instrument_pydantic_ai(include_content=True)
    _logfire_configured = True
