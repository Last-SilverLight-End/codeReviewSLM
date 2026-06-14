import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.core.config import settings
from app.core.log_store import log_store, setup_log_capture
from app.services.elasticsearch_logger import index_event

setup_log_capture()

app = FastAPI(title="Code Review AI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _log_requests(request: Request, call_next):
    # /admin/logs/stream은 로그에서 제외 (무한 재귀 방지)
    if request.url.path.endswith("/logs/stream") or request.url.path.endswith("/logs"):
        return await call_next(request)
    start = time.monotonic()
    try:
        response = await call_next(request)
    except Exception as exc:
        ms = int((time.monotonic() - start) * 1000)
        await index_event("api-error", {
            "method": request.method,
            "path": request.url.path,
            "duration_ms": ms,
            "error": exc.__class__.__name__,
        })
        raise
    ms = int((time.monotonic() - start) * 1000)
    level = "ERROR" if response.status_code >= 500 else "WARNING" if response.status_code >= 400 else "INFO"
    log_store.add(level, "HTTP", f"{request.method} {request.url.path} → {response.status_code} ({ms}ms)")
    await index_event("api-request", {
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "duration_ms": ms,
    })
    return response


app.include_router(v1_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"message": "Code Review AI API", "model": settings.OLLAMA_LLM_MODEL}
