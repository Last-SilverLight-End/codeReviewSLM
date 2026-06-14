import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import httpx

from app.core.config import settings
from app.core.log_store import log_store

router = APIRouter(prefix="/admin", tags=["admin"])

_EVENT_INDEX_PATTERNS = [
    "api-request",
    "llm-call",
    "rag-search",
    "web-search",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_service(name: str, url: str) -> dict[str, Any]:
    return {
        "name": name,
        "url": url,
        "ok": False,
        "status": "unknown",
        "detail": None,
    }


async def _get_elasticsearch_health(client: httpx.AsyncClient, base_url: str) -> dict[str, Any]:
    service = _empty_service("Elasticsearch", base_url)
    try:
        response = await client.get(f"{base_url}/_cluster/health")
        response.raise_for_status()
        body = response.json()
        status = body.get("status", "unknown")
        service.update({
            "ok": status in {"green", "yellow"},
            "status": status,
            "detail": {
                "cluster_name": body.get("cluster_name"),
                "number_of_nodes": body.get("number_of_nodes"),
                "active_shards": body.get("active_shards"),
            },
        })
    except Exception as exc:
        service["status"] = "down"
        service["detail"] = str(exc)
    return service


async def _get_kibana_status(client: httpx.AsyncClient, base_url: str) -> dict[str, Any]:
    service = _empty_service("Kibana", base_url)
    try:
        response = await client.get(f"{base_url}/api/status")
        response.raise_for_status()
        body = response.json()
        status = body.get("status", {}).get("overall", {}).get("level", "available")
        service.update({
            "ok": status in {"available", "degraded"},
            "status": status,
            "detail": {
                "version": body.get("version", {}).get("number"),
            },
        })
    except Exception as exc:
        service["status"] = "down"
        service["detail"] = str(exc)
    return service


async def _get_index_rows(client: httpx.AsyncClient, base_url: str) -> list[dict[str, Any]]:
    try:
        response = await client.get(
            f"{base_url}/_cat/indices/{settings.ELASTICSEARCH_LOG_INDEX_PREFIX}-*",
            params={
                "format": "json",
                "h": "health,status,index,docs.count,store.size",
                "s": "index",
            },
        )
        response.raise_for_status()
        rows = response.json()
    except Exception:
        return []

    normalized = []
    for row in rows:
        normalized.append({
            "health": row.get("health") or "unknown",
            "status": row.get("status") or "unknown",
            "index": row.get("index") or "",
            "docs_count": int(row.get("docs.count") or 0),
            "store_size": row.get("store.size") or "-",
        })
    return normalized


async def _get_recent_events(client: httpx.AsyncClient, base_url: str, limit: int = 20) -> list[dict[str, Any]]:
    patterns = ",".join(
        f"{settings.ELASTICSEARCH_LOG_INDEX_PREFIX}-{event_type}-*"
        for event_type in _EVENT_INDEX_PATTERNS
    )
    try:
        response = await client.post(
            f"{base_url}/{patterns}/_search",
            params={"ignore_unavailable": "true"},
            json={
                "size": limit,
                "sort": [{"@timestamp": {"order": "desc"}}],
                "_source": [
                    "@timestamp",
                    "event_type",
                    "route",
                    "method",
                    "path",
                    "status_code",
                    "duration_ms",
                    "model",
                    "purpose",
                    "tokens_input",
                    "tokens_output",
                    "project_id",
                    "top_k",
                    "result_count",
                    "filenames",
                    "error",
                ],
            },
        )
        response.raise_for_status()
        body = response.json()
    except Exception:
        return []

    events = []
    for hit in body.get("hits", {}).get("hits", []):
        source = hit.get("_source", {})
        events.append({
            "index": hit.get("_index"),
            "timestamp": source.get("@timestamp"),
            "event_type": source.get("event_type"),
            "route": source.get("route"),
            "method": source.get("method"),
            "path": source.get("path"),
            "status_code": source.get("status_code"),
            "duration_ms": source.get("duration_ms"),
            "model": source.get("model"),
            "purpose": source.get("purpose"),
            "tokens_input": source.get("tokens_input"),
            "tokens_output": source.get("tokens_output"),
            "project_id": source.get("project_id"),
            "top_k": source.get("top_k"),
            "result_count": source.get("result_count"),
            "filenames": source.get("filenames") or [],
            "error": source.get("error"),
        })
    return events


@router.get("/observability")
async def get_observability():
    """Elasticsearch/Kibana 기반 관리자 관측성 스냅샷."""
    elasticsearch_url = settings.ELASTICSEARCH_URL.rstrip("/")
    kibana_url = settings.KIBANA_URL.rstrip("/")
    async with httpx.AsyncClient(timeout=settings.ELASTICSEARCH_LOG_TIMEOUT) as client:
        elasticsearch, kibana, indexes, recent_events = await asyncio.gather(
            _get_elasticsearch_health(client, elasticsearch_url),
            _get_kibana_status(client, kibana_url),
            _get_index_rows(client, elasticsearch_url),
            _get_recent_events(client, elasticsearch_url),
        )

    error_count = sum(
        1
        for event in recent_events
        if (event.get("status_code") or 200) >= 400 or event.get("error")
    )
    rag_events = [event for event in recent_events if event.get("event_type") == "rag-search"]
    llm_events = [event for event in recent_events if event.get("event_type") == "llm-call"]
    return {
        "generated_at": _utc_now(),
        "kibana_url": kibana_url,
        "services": {
            "elasticsearch": elasticsearch,
            "kibana": kibana,
        },
        "summary": {
            "recent_event_count": len(recent_events),
            "recent_error_count": error_count,
            "recent_rag_count": len(rag_events),
            "recent_llm_count": len(llm_events),
            "index_count": len(indexes),
            "code_chunk_docs": next(
                (idx["docs_count"] for idx in indexes if idx["index"] == f"{settings.ELASTICSEARCH_LOG_INDEX_PREFIX}-code-chunks"),
                0,
            ),
        },
        "indexes": indexes,
        "recent_events": recent_events,
    }


@router.get("/logs/stream")
async def stream_logs():
    """실시간 로그 SSE 스트림."""
    async def event_generator():
        # 기존 히스토리 먼저 전송
        for entry in log_store.history():
            yield f"data: {json.dumps(entry.to_dict(), ensure_ascii=False)}\n\n"

        q = log_store.subscribe()
        try:
            while True:
                try:
                    entry = await asyncio.wait_for(q.get(), timeout=25.0)
                    yield f"data: {json.dumps(entry.to_dict(), ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            log_store.unsubscribe(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/logs")
async def get_logs():
    """로그 히스토리 스냅샷."""
    return [e.to_dict() for e in log_store.history()]


@router.delete("/logs", status_code=204)
async def clear_logs():
    """로그 초기화."""
    log_store.clear()
