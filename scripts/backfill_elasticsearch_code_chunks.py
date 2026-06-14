"""Backfill existing PostgreSQL code chunks into Elasticsearch BM25 index."""

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.code import CodeChunk, CodeFile
from app.services.elasticsearch_code_search import index_code_chunks


async def main() -> None:
    documents = []
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CodeChunk, CodeFile)
            .join(CodeFile, CodeChunk.file_id == CodeFile.id)
            .order_by(CodeChunk.id)
        )
        for chunk, code_file in result.all():
            documents.append({
                "chunk_id": chunk.id,
                "file_id": code_file.id,
                "user_id": code_file.user_id,
                "project_id": code_file.project_id,
                "filename": code_file.filename,
                "language": code_file.language,
                "chunk_type": chunk.chunk_type,
                "name": chunk.name,
                "content": chunk.content,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
            })

    await index_code_chunks(documents)
    print(f"indexed {len(documents)} code chunks")


if __name__ == "__main__":
    asyncio.run(main())
