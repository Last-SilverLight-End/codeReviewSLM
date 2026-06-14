import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings

_log = logging.getLogger("app.elasticsearch_logger")
_KNOWN_INDICES: set[str] = set()

_SENSITIVE_KEYS = {
    "authorization",
    "access_token",
    "refresh_token",
    "token",
    "password",
    "secret",
    "jwt",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _index_name(event_type: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y.%m.%d")
    safe_type = "".join(c if c.isalnum() or c in "-_" else "-" for c in event_type.lower())
    return f"{settings.ELASTICSEARCH_LOG_INDEX_PREFIX}-{safe_type}-{today}"


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in _SENSITIVE_KEYS:
                cleaned[key_text] = "[REDACTED]"
            else:
                cleaned[key_text] = _sanitize(item)
        return cleaned
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str) and len(value) > 500:
        return value[:500] + "...[truncated]"
    return value


async def index_event(event_type: str, payload: dict[str, Any]) -> None:
    """Store an operational event in Elasticsearch without breaking API flow."""
    if not settings.ELASTICSEARCH_LOG_ENABLED:
        return

    doc = {
        "@timestamp": _utc_now(),
        "service": "codereview-backend",
        "event_type": event_type,
        **_sanitize(payload),
    }

    index = _index_name(event_type)
    base_url = settings.ELASTICSEARCH_URL.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=settings.ELASTICSEARCH_LOG_TIMEOUT) as client:
            if index not in _KNOWN_INDICES:
                await client.put(
                    f"{base_url}/{index}",
                    json={"settings": {"number_of_shards": 1, "number_of_replicas": 0}},
                )
                _KNOWN_INDICES.add(index)
            url = f"{base_url}/{index}/_doc"
            response = await client.post(url, json=doc)
            response.raise_for_status()
    except Exception as exc:
        _log.debug("Elasticsearch log write skipped: %s", exc)


def schedule_log_event(event_type: str, payload: dict[str, Any]) -> None:
    """Fire-and-forget wrapper for request/LLM/RAG telemetry."""
    if not settings.ELASTICSEARCH_LOG_ENABLED:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(index_event(event_type, payload))
