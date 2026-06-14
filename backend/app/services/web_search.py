import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from app.core.config import settings
from app.services.elasticsearch_logger import schedule_log_event

_log = logging.getLogger("app.web_search")
_executor = ThreadPoolExecutor(max_workers=settings.WEB_SEARCH_MAX_WORKERS)


def _sync_search(query: str, max_results: int) -> list[dict]:
    from duckduckgo_search import DDGS
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            })
    return results


async def web_search(query: str, max_results: int = 5) -> list[dict]:
    """DuckDuckGo 검색 (비동기 래퍼). 결과: [{title, url, snippet}, ...]"""
    _log.info(f"[web_search] 검색: '{query}' (max={max_results})")
    loop = asyncio.get_event_loop()
    try:
        results = await loop.run_in_executor(_executor, _sync_search, query, max_results)
        _log.info(f"[web_search] {len(results)}개 결과 반환")
        schedule_log_event("web-search-provider", {
            "provider": "duckduckgo",
            "query_length": len(query),
            "max_results": max_results,
            "result_count": len(results),
            "status": "success",
        })
        return results
    except Exception as e:
        _log.warning(f"[web_search] 검색 실패: {e}")
        schedule_log_event("web-search-provider", {
            "provider": "duckduckgo",
            "query_length": len(query),
            "max_results": max_results,
            "result_count": 0,
            "status": "error",
            "error": e.__class__.__name__,
        })
        return []


def format_web_results(results: list[dict]) -> str:
    """검색 결과를 LLM 컨텍스트용 텍스트로 변환."""
    if not results:
        return "(검색 결과 없음)"
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}\n   URL: {r['url']}\n   {r['snippet']}")
    return "\n\n".join(lines)
