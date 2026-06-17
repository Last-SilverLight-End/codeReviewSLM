import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.celery_app import celery_app
from app.core.config import settings
from app.models.code import CodeChunk, CodeFile
from app.models.review import Review
from app.services.llm import generate_review
from app.services.vector_store import search_chunks_by_project

_DB_URL = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
_REVIEW_CONTEXT_TOP_K = 4


@celery_app.task(bind=True, max_retries=1)
def run_code_review(self, review_id: int, ollama_opts: dict | None = None):
    asyncio.run(_do_review(review_id, ollama_opts))


async def _do_review(review_id: int, ollama_opts: dict | None = None) -> None:
    # 태스크마다 새 엔진 생성 — 이벤트 루프 충돌 방지
    engine = create_async_engine(_DB_URL, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as db:
            review = await db.get(Review, review_id)
            if not review:
                return

            review.status = "processing"
            await db.commit()

            try:
                chunks_result = await db.execute(
                    select(CodeChunk).where(CodeChunk.file_id == review.file_id)
                )
                chunks = chunks_result.scalars().all()

                file = await db.get(CodeFile, review.file_id)
                filename = file.filename if file else "unknown"

                chunk_dicts = [
                    {
                        "chunk_type": c.chunk_type,
                        "name": c.name,
                        "content": c.content,
                        "start_line": c.start_line,
                        "end_line": c.end_line,
                    }
                    for c in chunks
                ]

                related_context = []
                if file and file.project_id is not None:
                    related_context = await _load_related_review_context(
                        db=db,
                        file=file,
                        chunks=chunk_dicts,
                    )

                result_text = await generate_review(
                    chunk_dicts,
                    filename,
                    options=ollama_opts,
                    related_context=related_context,
                )
                review.status = "completed"
                review.result = result_text

            except Exception as exc:
                review.status = "failed"
                review.error = str(exc)

            await db.commit()
    finally:
        await engine.dispose()


async def _load_related_review_context(
    db: AsyncSession,
    file: CodeFile,
    chunks: list[dict],
) -> list[dict]:
    query = _build_review_context_query(file.filename, chunks)
    if not query:
        return []

    results = await search_chunks_by_project(
        db=db,
        project_id=file.project_id,
        user_id=file.user_id,
        query=query,
        top_k=_REVIEW_CONTEXT_TOP_K * 2,
    )

    related = []
    for item in results:
        chunk = item.chunk
        if chunk.file_id == file.id:
            continue
        related.append({
            "filename": item.filename,
            "chunk_type": chunk.chunk_type,
            "name": chunk.name,
            "content": chunk.content,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
        })
        if len(related) >= _REVIEW_CONTEXT_TOP_K:
            break
    return related


def _build_review_context_query(filename: str, chunks: list[dict]) -> str:
    names = [str(chunk.get("name")) for chunk in chunks if chunk.get("name")]
    code_sample = "\n".join(str(chunk.get("content") or "")[:1200] for chunk in chunks[:3])
    return "\n".join([filename, " ".join(names), code_sample]).strip()[:5000]
