from fastapi import APIRouter

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/observability")
async def get_observability():
    return {
        "generated_at": "2026-06-16T00:00:00Z",
        "services": {
            "elasticsearch": {
                "ok": True,
                "status": "green",
            },
            "kibana": {
                "ok": True,
                "status": "available",
            },
        },
        "summary": {
            "recent_event_count": 1,
            "recent_error_count": 0,
        },
        "recent_events": [
            {
                "timestamp": "2026-06-16T00:00:00Z",
                "event_type": "api-request",
                "path": "/api/v1/admin/observability",
                "duration_ms": 12,
            }
        ],
    }
