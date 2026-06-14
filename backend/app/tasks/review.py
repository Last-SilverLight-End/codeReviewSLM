import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.celery_app import celery_app
from app.core.config import settings
from app.models.code import CodeChunk, CodeFile
from app.models.review import Review
from app.services.llm import generate_review

_DB_URL = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")


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

                result_text = await generate_review(chunk_dicts, filename, options=ollama_opts)
                review.status = "completed"
                review.result = result_text

            except Exception as exc:
                review.status = "failed"
                review.error = str(exc)

            await db.commit()
    finally:
        await engine.dispose()
