from __future__ import annotations

from src.vyu.observability.config import ObservabilitySettings


def configure_otel(settings: ObservabilitySettings | None = None) -> None:
    resolved = settings or ObservabilitySettings()
    if not resolved.otel_enabled:
        return

    try:
        from opentelemetry import metrics, trace
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:  # pragma: no cover - exercised when dependency missing
        raise RuntimeError(
            "OpenTelemetry packages are required when VYU_OTEL_ENABLED=true."
        ) from exc

    resource = Resource.create(
        {
            "service.name": resolved.service_name,
            "deployment.environment": resolved.environment,
        }
    )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=f"{resolved.otel_exporter_otlp_endpoint}/v1/traces")
        )
    )
    trace.set_tracer_provider(tracer_provider)

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=f"{resolved.otel_exporter_otlp_endpoint}/v1/metrics")
            )
        ],
    )
    metrics.set_meter_provider(meter_provider)
