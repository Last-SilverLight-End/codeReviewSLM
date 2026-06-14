import logging
from typing import Any

import httpx

from app.core.config import settings

_log = logging.getLogger("app.elasticsearch_code_search")

CODE_CHUNK_INDEX = "codereview-code-chunks"


def _base_url() -> str:
    return settings.ELASTICSEARCH_URL.rstrip("/")


async def ensure_code_chunk_index() -> None:
    if not settings.ELASTICSEARCH_LOG_ENABLED:
        return

    mapping = {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        },
        "mappings": {
            "properties": {
                "chunk_id": {"type": "long"},
                "file_id": {"type": "long"},
                "user_id": {"type": "long"},
                "project_id": {"type": "long"},
                "filename": {"type": "keyword"},
                "filename_text": {"type": "text"},
                "language": {"type": "keyword"},
                "chunk_type": {"type": "keyword"},
                "name": {"type": "text"},
                "name_keyword": {"type": "keyword"},
                "content": {"type": "text"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
            }
        },
    }

    try:
        async with httpx.AsyncClient(timeout=settings.ELASTICSEARCH_LOG_TIMEOUT) as client:
            response = await client.head(f"{_base_url()}/{CODE_CHUNK_INDEX}")
            if response.status_code == 404:
                create = await client.put(f"{_base_url()}/{CODE_CHUNK_INDEX}", json=mapping)
                create.raise_for_status()
    except Exception as exc:
        _log.debug("Code chunk index check skipped: %s", exc)


async def index_code_chunks(documents: list[dict[str, Any]]) -> None:
    """Index code chunks for BM25/full-text retrieval. Best-effort by design."""
    if not settings.ELASTICSEARCH_LOG_ENABLED or not documents:
        return

    await ensure_code_chunk_index()
    lines: list[str] = []
    for doc in documents:
        chunk_id = doc["chunk_id"]
        action = {"index": {"_index": CODE_CHUNK_INDEX, "_id": str(chunk_id)}}
        body = {
            **doc,
            "filename_text": doc.get("filename", ""),
            "name_keyword": doc.get("name") or "",
        }
        lines.append(_json_line(action))
        lines.append(_json_line(body))
    payload = "\n".join(lines) + "\n"

    try:
        async with httpx.AsyncClient(timeout=max(settings.ELASTICSEARCH_LOG_TIMEOUT, 5.0)) as client:
            response = await client.post(
                f"{_base_url()}/_bulk",
                content=payload,
                headers={"Content-Type": "application/x-ndjson"},
            )
            response.raise_for_status()
            body = response.json()
            if body.get("errors"):
                _log.warning("Some code chunks failed Elasticsearch indexing")
    except Exception as exc:
        _log.debug("Code chunk indexing skipped: %s", exc)


async def search_code_chunk_ids(
    query: str,
    user_id: int,
    project_id: int | None = None,
    top_k: int = 20,
    include_all_projects: bool = False,
) -> list[tuple[int, float]]:
    """Return chunk IDs ranked by Elasticsearch BM25 score."""
    if not settings.ELASTICSEARCH_LOG_ENABLED:
        return []

    filters: list[dict[str, Any]] = [{"term": {"user_id": user_id}}]
    if include_all_projects:
        pass
    elif project_id is None:
        filters.append({"bool": {"must_not": {"exists": {"field": "project_id"}}}})
    else:
        filters.append({"term": {"project_id": project_id}})

    body = {
        "size": top_k,
        "_source": ["chunk_id"],
        "query": {
            "bool": {
                "filter": filters,
                "must": [
                    {
                        "multi_match": {
                            "query": query,
                            "fields": [
                                "content^2",
                                "name^4",
                                "filename_text^3",
                                "chunk_type",
                                "language",
                            ],
                            "type": "best_fields",
                            "operator": "or",
                        }
                    }
                ],
            }
        },
    }

    try:
        async with httpx.AsyncClient(timeout=settings.ELASTICSEARCH_LOG_TIMEOUT) as client:
            response = await client.post(f"{_base_url()}/{CODE_CHUNK_INDEX}/_search", json=body)
            if response.status_code == 404:
                return []
            response.raise_for_status()
            hits = response.json().get("hits", {}).get("hits", [])
    except Exception as exc:
        _log.debug("Code chunk BM25 search skipped: %s", exc)
        return []

    results: list[tuple[int, float]] = []
    for hit in hits:
        chunk_id = hit.get("_source", {}).get("chunk_id")
        if isinstance(chunk_id, int):
            results.append((chunk_id, float(hit.get("_score") or 0.0)))
    return results


def _json_line(data: dict[str, Any]) -> str:
    import json

    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
