from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.code import CodeFile
from app.models.review import Review
from app.models.user import User
from app.schemas.review import QuickReviewResponse, ReviewRequest, ReviewResponse
from app.services import parser as parser_svc
from app.services.llm import generate_review
from app.tasks.review import run_code_review

router = APIRouter(prefix="/review", tags=["review"])


@router.post("/quick", response_model=QuickReviewResponse)
async def quick_review(file: UploadFile):
    """로그인 없이 즉시 코드 리뷰 (DB 저장 없음)."""
    content = (await file.read()).decode("utf-8", errors="replace")
    filename = file.filename or "unknown"

    language = parser_svc.detect_language(filename)
    if language is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"지원하지 않는 파일 형식입니다. 지원: {parser_svc.SUPPORTED_EXTENSIONS_TEXT}",
        )

    chunks = parser_svc.parse_code(content, language)
    chunk_dicts = [
        {"chunk_type": c.chunk_type, "name": c.name, "content": c.content,
         "start_line": c.start_line, "end_line": c.end_line}
        for c in chunks
    ]
    result = await generate_review(chunk_dicts, filename)
    return QuickReviewResponse(filename=filename, language=language, result=result)


@router.post("/", response_model=ReviewResponse, status_code=status.HTTP_202_ACCEPTED)
async def request_review(
    body: ReviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 파일 존재 + 소유권 확인
    file = await db.get(CodeFile, body.file_id)
    if not file or file.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="파일을 찾을 수 없습니다.")

    review = Review(user_id=current_user.id, file_id=body.file_id, status="pending")
    db.add(review)
    await db.commit()
    await db.refresh(review)

    # Celery 태스크 큐
    ollama_opts = body.model_options.to_ollama_options(default_temperature=0.2)
    task = run_code_review.delay(review.id, ollama_opts)
    review.celery_task_id = task.id
    await db.commit()
    await db.refresh(review)

    return review


@router.get("/{review_id}", response_model=ReviewResponse)
async def get_review(
    review_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    review = await db.get(Review, review_id)
    if not review or review.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="리뷰를 찾을 수 없습니다.")
    return review
