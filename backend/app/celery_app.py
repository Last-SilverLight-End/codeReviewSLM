from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "codereview",
    broker=settings.REDIS_URL,
    include=["app.tasks.review"],
)

celery_app.conf.update(
    task_ignore_result=True,
    task_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=True,
)
