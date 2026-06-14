from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.code import router as code_router
from app.api.v1.review import router as review_router

router = APIRouter()
router.include_router(admin_router)
router.include_router(auth_router)
router.include_router(chat_router)
router.include_router(code_router)
router.include_router(review_router)


@router.get("/health")
async def health_check():
    return {"status": "ok"}
