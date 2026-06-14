from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.project import Project
from app.models.user import User
from app.schemas.code import ProjectResponse, ProjectUploadResponse, SearchResponse, UploadResponse
from app.services import parser as parser_svc
from app.services import project_parser as project_parser_svc
from app.services import vector_store as vs
from app.services.elasticsearch_code_search import index_code_chunks
from app.services.elasticsearch_logger import schedule_log_event

router = APIRouter(prefix="/code", tags=["code"])


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_code(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    content = (await file.read()).decode("utf-8", errors="replace")
    filename = file.filename or "unknown"

    language = parser_svc.detect_language(filename)
    if language is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"지원하지 않는 파일 형식입니다. 지원: {parser_svc.SUPPORTED_EXTENSIONS_TEXT}",
        )

    # 파싱
    chunks = parser_svc.parse_code(content, language)

    # DB 저장 + 임베딩
    await vs.ensure_vector_extension(db)
    code_file = await vs.save_code_file(db, current_user.id, filename, language, content)
    indexed_docs = []

    for chunk in chunks:
        saved_chunk = await vs.save_chunk_with_embedding(
            db,
            file_id=code_file.id,
            chunk_type=chunk.chunk_type,
            name=chunk.name,
            content=chunk.content,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
        )
        await db.flush()
        indexed_docs.append(_chunk_index_doc(saved_chunk, code_file, current_user.id))

    await db.commit()
    await index_code_chunks(indexed_docs)

    return UploadResponse(
        file_id=code_file.id,
        filename=filename,
        language=language,
        chunk_count=len(chunks),
    )


@router.post("/upload-project", response_model=ProjectUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_project(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="zip 파일만 업로드 가능합니다.",
        )

    zip_bytes = await file.read()
    parsed_files = project_parser_svc.parse_zip(zip_bytes)

    if not parsed_files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"지원하는 소스 파일이 없습니다. ({parser_svc.SUPPORTED_EXTENSIONS_TEXT})",
        )

    project_name = file.filename.removesuffix(".zip")
    project = Project(
        user_id=current_user.id,
        name=project_name,
        file_count=0,
        chunk_count=0,
    )
    db.add(project)
    await db.flush()

    await vs.ensure_vector_extension(db)

    total_chunks = 0
    indexed_docs = []
    for pf in parsed_files:
        code_file = await vs.save_code_file_with_project(
            db,
            user_id=current_user.id,
            project_id=project.id,
            filename=pf.filename,
            language=pf.language,
            content=pf.content,
        )
        for chunk in pf.chunks:
            saved_chunk = await vs.save_chunk_with_embedding(
                db,
                file_id=code_file.id,
                chunk_type=chunk.chunk_type,
                name=chunk.name,
                content=chunk.content,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
            )
            await db.flush()
            indexed_docs.append(_chunk_index_doc(saved_chunk, code_file, current_user.id))
        total_chunks += len(pf.chunks)

    project.file_count = len(parsed_files)
    project.chunk_count = total_chunks
    await db.commit()
    await index_code_chunks(indexed_docs)

    return ProjectUploadResponse(
        project_id=project.id,
        name=project_name,
        file_count=len(parsed_files),
        chunk_count=total_chunks,
    )


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project)
        .where(Project.user_id == current_user.id)
        .order_by(Project.created_at.desc())
    )
    projects = result.scalars().all()
    return [
        ProjectResponse(
            id=project.id,
            name=project.name,
            file_count=project.file_count,
            chunk_count=project.chunk_count,
            created_at=project.created_at.isoformat(),
        )
        for project in projects
    ]


@router.get("/search", response_model=SearchResponse)
async def search_code(
    q: str = Query(..., description="검색할 코드 또는 자연어 쿼리"),
    top_k: int = Query(5, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    started_at = perf_counter()
    chunks = await vs.search_similar_chunks(db, query=q, top_k=top_k, user_id=current_user.id)
    schedule_log_event(
        "rag-search",
        {
            "route": "/api/v1/code/search",
            "mode": "hybrid-code-search",
            "user_id": current_user.id,
            "query_length": len(q),
            "top_k": top_k,
            "result_count": len(chunks),
            "duration_ms": int((perf_counter() - started_at) * 1000),
        },
    )
    return SearchResponse(chunks=chunks)


def _chunk_index_doc(chunk, code_file, user_id: int) -> dict:
    return {
        "chunk_id": chunk.id,
        "file_id": code_file.id,
        "user_id": user_id,
        "project_id": code_file.project_id,
        "filename": code_file.filename,
        "language": code_file.language,
        "chunk_type": chunk.chunk_type,
        "name": chunk.name,
        "content": chunk.content,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
    }
