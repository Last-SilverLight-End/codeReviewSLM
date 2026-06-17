from __future__ import annotations

import asyncio
import io
import sys
import time
import zipfile
from pathlib import Path

import httpx
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.database import AsyncSessionLocal, engine  # noqa: E402
from app.models.code import CodeFile  # noqa: E402
from app.tasks.review import _load_related_review_context  # noqa: E402

API_BASE = "http://localhost:8000/api/v1"

BROKEN_DASHBOARD = """<!doctype html>
<html lang="ko">
<body>
  <p id="status">Loading...</p>
  <table><tbody id="events"></tbody></table>
  <script>
    const API_BASE = "http://localhost:8000/api/v1";
    async function refreshLogs() {
      const status = document.getElementById("status");
      const events = document.getElementById("events");
      const response = await fetch(API_BASE + "/admin/observability");
      const data = await response.json();
      status.innerHTML = "Cluster: " + data.elasticsearch.status;
      events.innerHTML = "";
      data.recent_events.forEach((event) => {
        const row = document.createElement("tr");
        row.innerHTML = "<td>" + event.timestamp + "</td><td>" + event.message + "</td>";
        events.appendChild(row);
      });
    }
  </script>
</body>
</html>
"""

ADMIN_API = '''from fastapi import APIRouter

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/observability")
async def get_observability():
    return {
        "generated_at": "2026-06-16T00:00:00Z",
        "services": {
            "elasticsearch": {"status": "green", "ok": True},
            "kibana": {"status": "available", "ok": True},
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
'''

ADMIN_PAGE = """type ObservabilitySnapshot = {
  services: {
    elasticsearch: { status: string; ok: boolean };
    kibana: { status: string; ok: boolean };
  };
  recent_events: Array<{
    timestamp: string;
    event_type: string;
    path?: string | null;
    duration_ms?: number | null;
    error?: string | null;
  }>;
};

function render(snapshot: ObservabilitySnapshot) {
  return `${snapshot.services.elasticsearch.status} ${snapshot.recent_events.length}`;
}
"""


async def main() -> int:
    stamp = int(time.time())
    email = f"rag-probe-{stamp}@example.com"
    password = "rag-probe-pass"
    zip_bytes = build_zip(stamp)

    async with httpx.AsyncClient(timeout=35.0) as client:
        register = await client.post(f"{API_BASE}/auth/register", json={"email": email, "password": password})
        if register.status_code not in {201, 409}:
            print(f"REGISTER_FAIL {register.status_code} {register.text[:300]}")
            return 1

        login = await client.post(f"{API_BASE}/auth/login", json={"email": email, "password": password})
        if login.status_code != 200:
            print(f"LOGIN_FAIL {login.status_code} {login.text[:300]}")
            return 1
        token = login.json()["access_token"]

        upload = await client.post(
            f"{API_BASE}/code/upload-project",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (f"rag_probe_{stamp}.zip", zip_bytes, "application/zip")},
        )
        if upload.status_code != 201:
            print(f"UPLOAD_FAIL {upload.status_code} {upload.text[:500]}")
            return 1

    payload = upload.json()
    project_id = payload["project_id"]
    target_name = f"broken_dashboard_rag_probe_{stamp}.html"
    print(f"UPLOAD_OK project_id={project_id} file_count={payload['file_count']} chunk_count={payload['chunk_count']}")

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CodeFile)
            .where(CodeFile.project_id == project_id, CodeFile.filename == target_name)
            .limit(1)
        )
        file = result.scalar_one_or_none()
        if file is None:
            print("TARGET_NOT_FOUND")
            return 1

        chunks = [{
            "chunk_type": "module",
            "name": None,
            "content": file.content,
            "start_line": 1,
            "end_line": file.content.count("\n") + 1,
        }]
        related = await _load_related_review_context(db, file, chunks)

    print(f"RELATED_COUNT {len(related)}")
    for index, item in enumerate(related, start=1):
        print(
            "RELATED "
            f"{index} filename={item['filename']} "
            f"type={item['chunk_type']} "
            f"name={item['name']} "
            f"lines={item['start_line']}-{item['end_line']}"
        )

    joined = "\n".join(item["content"] for item in related)
    checks = {
        "services.elasticsearch.status": "services" in joined and "elasticsearch" in joined and "status" in joined,
        "recent_events_shape": "recent_events" in joined and "event_type" in joined,
        "frontend_snapshot_usage": "ObservabilitySnapshot" in joined or "snapshot.services.elasticsearch.status" in joined,
    }
    for name, ok in checks.items():
        print(f"CHECK {name} {'PASS' if ok else 'FAIL'}")

    return 0 if all(checks.values()) else 1


def build_zip(stamp: int) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"broken_dashboard_rag_probe_{stamp}.html", BROKEN_DASHBOARD)
        zf.writestr("backend/app/api/v1/admin_observability_sample.py", ADMIN_API)
        zf.writestr("frontend/app/admin/observability_sample.ts", ADMIN_PAGE)
    return buffer.getvalue()


if __name__ == "__main__":
    async def _run() -> int:
        try:
            return await main()
        finally:
            await engine.dispose()

    raise SystemExit(asyncio.run(_run()))
