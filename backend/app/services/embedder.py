import httpx

from app.core.config import settings

_OLLAMA_EMBED_URL = f"{settings.OLLAMA_BASE_URL}{settings.OLLAMA_EMBED_ENDPOINT}"


async def get_embedding(text: str) -> list[float]:
    """Ollama nomic-embed-code로 코드 텍스트를 768차원 벡터로 변환."""
    async with httpx.AsyncClient(timeout=settings.OLLAMA_EMBED_TIMEOUT) as client:
        response = await client.post(
            _OLLAMA_EMBED_URL,
            json={"model": settings.OLLAMA_EMBED_MODEL, "input": text},
        )
        response.raise_for_status()
        data = response.json()
        # Ollama /api/embed 응답: {"embeddings": [[...]], ...}
        return data["embeddings"][0]


async def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """여러 텍스트를 순차적으로 임베딩. (Ollama는 배치 미지원)"""
    results = []
    for text in texts:
        embedding = await get_embedding(text)
        results.append(embedding)
    return results
