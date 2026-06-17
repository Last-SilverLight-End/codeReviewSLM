from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx
from sqlalchemy import delete, select

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionLocal, engine  # noqa: E402
from app.models.code import CodeChunk, CodeFile  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.review import Review  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.elasticsearch_code_search import CODE_CHUNK_INDEX  # noqa: E402


TEST_EMAIL_PREFIXES = ("rag-probe-",)
TEST_PROJECT_PREFIXES = ("rag_probe_",)
TEST_FILENAMES = (
    "broken_dashboard_rag_probe_",
    "backend/app/api/v1/admin_observability_sample.py",
    "frontend/app/admin/observability_sample.ts",
)


async def main() -> int:
    async with AsyncSessionLocal() as db:
        user_ids = await _find_test_user_ids(db)
        project_ids = await _find_test_project_ids(db, user_ids)
        file_ids = await _find_test_file_ids(db, user_ids, project_ids)

        await _delete_elasticsearch_docs(user_ids, project_ids, file_ids)

        if file_ids:
            await db.execute(delete(Review).where(Review.file_id.in_(file_ids)))
            await db.execute(delete(CodeChunk).where(CodeChunk.file_id.in_(file_ids)))
            await db.execute(delete(CodeFile).where(CodeFile.id.in_(file_ids)))

        if project_ids:
            await db.execute(delete(Project).where(Project.id.in_(project_ids)))

        if user_ids:
            await db.execute(delete(User).where(User.id.in_(user_ids)))

        await db.commit()

        print(f"deleted_users={len(user_ids)}")
        print(f"deleted_projects={len(project_ids)}")
        print(f"deleted_files={len(file_ids)}")
    return 0


async def _find_test_user_ids(db) -> list[int]:
    result = await db.execute(select(User.id, User.email))
    return [
        row.id
        for row in result.all()
        if any(row.email.startswith(prefix) for prefix in TEST_EMAIL_PREFIXES)
    ]


async def _find_test_project_ids(db, user_ids: list[int]) -> list[int]:
    stmt = select(Project.id, Project.name)
    if user_ids:
        stmt = stmt.where(Project.user_id.in_(user_ids))
    result = await db.execute(stmt)
    return [
        row.id
        for row in result.all()
        if any(row.name.startswith(prefix) for prefix in TEST_PROJECT_PREFIXES)
    ]


async def _find_test_file_ids(db, user_ids: list[int], project_ids: list[int]) -> list[int]:
    conditions = []
    if user_ids:
        conditions.append(CodeFile.user_id.in_(user_ids))
    if project_ids:
        conditions.append(CodeFile.project_id.in_(project_ids))

    result = await db.execute(select(CodeFile.id, CodeFile.filename, CodeFile.user_id, CodeFile.project_id))
    ids = []
    for row in result.all():
        filename_match = any(row.filename.startswith(prefix) for prefix in TEST_FILENAMES)
        linked_match = (user_ids and row.user_id in user_ids) or (project_ids and row.project_id in project_ids)
        if filename_match or linked_match:
            ids.append(row.id)
    return ids


async def _delete_elasticsearch_docs(user_ids: list[int], project_ids: list[int], file_ids: list[int]) -> None:
    should = []
    if user_ids:
        should.append({"terms": {"user_id": user_ids}})
    if project_ids:
        should.append({"terms": {"project_id": project_ids}})
    if file_ids:
        should.append({"terms": {"file_id": file_ids}})
    if not should:
        return

    body = {"query": {"bool": {"should": should, "minimum_should_match": 1}}}
    url = f"{settings.ELASTICSEARCH_URL.rstrip('/')}/{CODE_CHUNK_INDEX}/_delete_by_query"
    try:
        async with httpx.AsyncClient(timeout=max(settings.ELASTICSEARCH_LOG_TIMEOUT, 5.0)) as client:
            response = await client.post(url, params={"conflicts": "proceed", "refresh": "true"}, json=body)
            if response.status_code != 404:
                response.raise_for_status()
                deleted = response.json().get("deleted", 0)
                print(f"deleted_elasticsearch_docs={deleted}")
    except Exception as exc:
        print(f"elasticsearch_cleanup_skipped={exc}")


if __name__ == "__main__":
    async def _run() -> int:
        try:
            return await main()
        finally:
            await engine.dispose()

    raise SystemExit(asyncio.run(_run()))
