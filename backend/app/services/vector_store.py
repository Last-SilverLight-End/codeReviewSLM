from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.code import CodeChunk, CodeFile
from app.services.elasticsearch_code_search import search_code_chunk_ids
from app.services.embedder import get_embedding


@dataclass
class ChunkWithFile:
    chunk: CodeChunk
    filename: str


async def ensure_vector_extension(db: AsyncSession) -> None:
    """pgvector 익스텐션 활성화 (최초 1회)."""
    await db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    await db.commit()


async def save_code_file_with_project(
    db: AsyncSession,
    user_id: int,
    project_id: int,
    filename: str,
    language: str,
    content: str,
) -> CodeFile:
    code_file = CodeFile(
        user_id=user_id,
        project_id=project_id,
        filename=filename,
        language=language,
        content=content,
    )
    db.add(code_file)
    await db.flush()
    return code_file


async def search_chunks_by_project(
    db: AsyncSession,
    project_id: int,
    user_id: int,
    query: str,
    top_k: int = 5,
) -> list[ChunkWithFile]:
    """프로젝트 내 코드를 Elasticsearch BM25 + pgvector 의미 검색으로 반환."""
    vector_results = await _vector_chunks_by_project(db, project_id, user_id, query, max(top_k * 3, 10))
    elastic_results = await search_code_chunk_ids(
        query=query,
        user_id=user_id,
        project_id=project_id,
        top_k=max(top_k * 4, 20),
    )
    return await _fuse_project_results(
        db,
        project_id=project_id,
        user_id=user_id,
        vector_results=vector_results,
        elastic_results=elastic_results,
        top_k=top_k,
    )


async def _vector_chunks_by_project(
    db: AsyncSession,
    project_id: int,
    user_id: int,
    query: str,
    top_k: int,
) -> list[ChunkWithFile]:
    query_embedding = await get_embedding(query)

    stmt = (
        select(CodeChunk, CodeFile.filename)
        .join(CodeFile, CodeChunk.file_id == CodeFile.id)
        .where(
            CodeFile.project_id == project_id,
            CodeFile.user_id == user_id,
            CodeChunk.embedding.is_not(None),
        )
        .order_by(CodeChunk.embedding.cosine_distance(query_embedding))
        .limit(top_k)
    )
    result = await db.execute(stmt)
    return [ChunkWithFile(chunk=row[0], filename=row[1]) for row in result.all()]


async def _fuse_project_results(
    db: AsyncSession,
    project_id: int,
    user_id: int,
    vector_results: list[ChunkWithFile],
    elastic_results: list[tuple[int, float]],
    top_k: int,
) -> list[ChunkWithFile]:
    scores: dict[int, float] = {}
    rank_constant = settings.HYBRID_RRF_RANK_CONSTANT
    vector_weight = settings.HYBRID_VECTOR_WEIGHT
    elastic_weight = settings.HYBRID_ELASTICSEARCH_WEIGHT

    by_id = {item.chunk.id: item for item in vector_results}
    for rank, item in enumerate(vector_results, start=1):
        scores[item.chunk.id] = scores.get(item.chunk.id, 0.0) + vector_weight / (rank_constant + rank)

    missing_elastic_ids: list[int] = []
    for rank, (chunk_id, _score) in enumerate(elastic_results, start=1):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + elastic_weight / (rank_constant + rank)
        if chunk_id not in by_id:
            missing_elastic_ids.append(chunk_id)

    if missing_elastic_ids:
        loaded = await _load_project_chunks_by_ids(db, project_id, user_id, missing_elastic_ids)
        by_id.update({item.chunk.id: item for item in loaded})

    ranked_ids = sorted(scores, key=lambda chunk_id: scores[chunk_id], reverse=True)
    return [by_id[chunk_id] for chunk_id in ranked_ids if chunk_id in by_id][:top_k]


async def _load_project_chunks_by_ids(
    db: AsyncSession,
    project_id: int,
    user_id: int,
    chunk_ids: list[int],
) -> list[ChunkWithFile]:
    if not chunk_ids:
        return []
    stmt = (
        select(CodeChunk, CodeFile.filename)
        .join(CodeFile, CodeChunk.file_id == CodeFile.id)
        .where(
            CodeChunk.id.in_(chunk_ids),
            CodeFile.project_id == project_id,
            CodeFile.user_id == user_id,
        )
    )
    result = await db.execute(stmt)
    rows = [ChunkWithFile(chunk=row[0], filename=row[1]) for row in result.all()]
    order = {chunk_id: index for index, chunk_id in enumerate(chunk_ids)}
    return sorted(rows, key=lambda item: order.get(item.chunk.id, len(order)))


async def save_code_file(
    db: AsyncSession,
    user_id: int,
    filename: str,
    language: str,
    content: str,
) -> CodeFile:
    code_file = CodeFile(
        user_id=user_id,
        filename=filename,
        language=language,
        content=content,
    )
    db.add(code_file)
    await db.flush()  # id 확보
    return code_file


async def save_chunk_with_embedding(
    db: AsyncSession,
    file_id: int,
    chunk_type: str,
    name: str | None,
    content: str,
    start_line: int,
    end_line: int,
) -> CodeChunk:
    embedding = await get_embedding(content)
    chunk = CodeChunk(
        file_id=file_id,
        chunk_type=chunk_type,
        name=name,
        content=content,
        start_line=start_line,
        end_line=end_line,
        embedding=embedding,
    )
    db.add(chunk)
    return chunk


async def search_similar_chunks(
    db: AsyncSession,
    query: str,
    top_k: int = 5,
    user_id: int | None = None,
) -> list[CodeChunk]:
    """쿼리와 유사한 코드 청크를 Elasticsearch BM25 + pgvector로 반환."""
    vector_chunks = await _vector_similar_chunks(db, query=query, top_k=max(top_k * 3, 10), user_id=user_id)
    if user_id is None:
        return vector_chunks[:top_k]

    elastic_results = await search_code_chunk_ids(
        query=query,
        user_id=user_id,
        top_k=max(top_k * 4, 20),
        include_all_projects=True,
    )
    return await _fuse_chunk_results(
        db,
        user_id=user_id,
        vector_results=vector_chunks,
        elastic_results=elastic_results,
        top_k=top_k,
    )


async def _vector_similar_chunks(
    db: AsyncSession,
    query: str,
    top_k: int,
    user_id: int | None,
) -> list[CodeChunk]:
    query_embedding = await get_embedding(query)

    stmt = (
        select(CodeChunk)
        .join(CodeFile, CodeChunk.file_id == CodeFile.id)
        .where(CodeChunk.embedding.is_not(None))
        .order_by(CodeChunk.embedding.cosine_distance(query_embedding))
        .limit(top_k)
    )
    if user_id is not None:
        stmt = stmt.where(CodeFile.user_id == user_id)

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _fuse_chunk_results(
    db: AsyncSession,
    user_id: int,
    vector_results: list[CodeChunk],
    elastic_results: list[tuple[int, float]],
    top_k: int,
) -> list[CodeChunk]:
    scores: dict[int, float] = {}
    rank_constant = settings.HYBRID_RRF_RANK_CONSTANT
    vector_weight = settings.HYBRID_VECTOR_WEIGHT
    elastic_weight = settings.HYBRID_ELASTICSEARCH_WEIGHT
    by_id = {chunk.id: chunk for chunk in vector_results}

    for rank, chunk in enumerate(vector_results, start=1):
        scores[chunk.id] = scores.get(chunk.id, 0.0) + vector_weight / (rank_constant + rank)

    missing_elastic_ids: list[int] = []
    for rank, (chunk_id, _score) in enumerate(elastic_results, start=1):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + elastic_weight / (rank_constant + rank)
        if chunk_id not in by_id:
            missing_elastic_ids.append(chunk_id)

    if missing_elastic_ids:
        loaded = await _load_user_chunks_by_ids(db, user_id, missing_elastic_ids)
        by_id.update({chunk.id: chunk for chunk in loaded})

    ranked_ids = sorted(scores, key=lambda chunk_id: scores[chunk_id], reverse=True)
    return [by_id[chunk_id] for chunk_id in ranked_ids if chunk_id in by_id][:top_k]


async def _load_user_chunks_by_ids(
    db: AsyncSession,
    user_id: int,
    chunk_ids: list[int],
) -> list[CodeChunk]:
    if not chunk_ids:
        return []
    stmt = (
        select(CodeChunk)
        .join(CodeFile, CodeChunk.file_id == CodeFile.id)
        .where(
            CodeChunk.id.in_(chunk_ids),
            CodeFile.user_id == user_id,
        )
    )
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    order = {chunk_id: index for index, chunk_id in enumerate(chunk_ids)}
    return sorted(rows, key=lambda chunk: order.get(chunk.id, len(order)))
