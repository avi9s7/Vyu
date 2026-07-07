from __future__ import annotations

import json
from datetime import datetime, timezone

from openai.types.responses import Response

from src.vyu.model_gateway.contracts import ModelRequest, ModelResponse
from src.vyu.model_gateway.errors import GatewayMalformedResponse, GatewayPolicyBlocked

STRUCTURED_OUTPUT_MODEL_PREFIXES = (
    "gpt-4o",
    "gpt-4.1",
    "gpt-5",
    "o3",
    "o4",
)


def supports_openai_structured_synthesis(model_id: str) -> bool:
    normalized = model_id.strip().lower()
    return any(normalized.startswith(prefix) for prefix in STRUCTURED_OUTPUT_MODEL_PREFIXES)


def normalize_openai_generation_response(
    request: ModelRequest,
    response: Response,
    *,
    latency_ms: int,
) -> ModelResponse:
    if response.status in {"failed", "cancelled"}:
        raise GatewayMalformedResponse(f"provider response status is {response.status}")
    if response.status == "incomplete" or response.incomplete_details is not None:
        raise GatewayMalformedResponse("provider returned incomplete output")

    refusals = _extract_openai_refusals(response)
    if refusals:
        raise GatewayPolicyBlocked("provider refused the request")

    output_text = response.output_text
    if not output_text.strip():
        raise GatewayMalformedResponse("provider returned empty structured output")

    try:
        output = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise GatewayMalformedResponse("provider returned non-json output") from exc
    if not isinstance(output, dict):
        raise GatewayMalformedResponse("provider structured output must be a JSON object")

    usage = response.usage
    input_tokens = usage.input_tokens if usage is not None else 0
    output_tokens = usage.output_tokens if usage is not None else 0
    reasoning_tokens = (
        usage.output_tokens_details.reasoning_tokens
        if usage is not None and usage.output_tokens_details is not None
        else 0
    )
    cached_tokens = (
        usage.input_tokens_details.cached_tokens
        if usage is not None and usage.input_tokens_details is not None
        else 0
    )

    return ModelResponse.from_output(
        request=request,
        provider_request_id=response.id,
        output=output,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        cached_tokens=cached_tokens,
        latency_ms=latency_ms,
        finish_reason=_openai_finish_reason(response),
        schema_valid=True,
    )


def schema_name(prompt_template_id: str) -> str:
    sanitized = "".join(
        character if character.isalnum() or character in {"_", "-"} else "_"
        for character in prompt_template_id.strip()
    )
    return (sanitized or "vyu_output")[:64]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_openai_refusals(response: Response) -> list[str]:
    refusals: list[str] = []
    for item in response.output:
        if item.type != "message":
            continue
        for content in item.content:
            if content.type == "refusal":
                refusals.append(content.refusal)
    return refusals


def _openai_finish_reason(response: Response) -> str:
    if response.status == "completed":
        return "stop"
    if response.status == "incomplete":
        return "incomplete"
    return str(response.status or "unknown")
