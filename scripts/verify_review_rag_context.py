from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.database import AsyncSessionLocal, engine  # noqa: E402
from app.models.code import CodeFile  # noqa: E402
from app.tasks.review import _build_review_context_query, _load_related_review_context  # noqa: E402


async def main() -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CodeFile)
            .where(CodeFile.filename.like("%broken_dashboard%"))
            .order_by(CodeFile.id.desc())
            .limit(1)
        )
        file = result.scalar_one_or_none()

        if file is None:
            print("NO_BROKEN_DASHBOARD_IN_DB")
            await print_recent_files(db)
            return 2

        chunks = [
            {
                "chunk_type": "module",
                "name": None,
                "content": file.content,
                "start_line": 1,
                "end_line": file.content.count("\n") + 1,
            }
        ]
        query = _build_review_context_query(file.filename, chunks)
        related = await _load_related_review_context(db, file, chunks)

        print(f"TARGET file_id={file.id} project_id={file.project_id} filename={file.filename}")
        print(f"QUERY_LENGTH {len(query)}")
        print(f"RELATED_COUNT {len(related)}")
        for index, item in enumerate(related, start=1):
            print(
                "RELATED "
                f"{index} filename={item['filename']} "
                f"type={item['chunk_type']} "
                f"name={item['name']} "
                f"lines={item['start_line']}-{item['end_line']}"
            )
        return 0 if related else 1


async def print_recent_files(db) -> None:
    result = await db.execute(
        select(CodeFile.id, CodeFile.filename, CodeFile.project_id)
        .order_by(CodeFile.id.desc())
        .limit(10)
    )
    print("RECENT_FILES")
    for row in result.all():
        print(dict(row._mapping))


if __name__ == "__main__":
    async def _run() -> int:
        try:
            return await main()
        finally:
            await engine.dispose()

    raise SystemExit(asyncio.run(_run()))
