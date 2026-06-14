import redis.asyncio as aioredis

from app.core.config import settings

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def set_refresh_token(user_id: int, token: str, expire_days: int) -> None:
    r = await get_redis()
    key = f"refresh_token:{user_id}"
    await r.setex(key, expire_days * 86400, token)


async def get_refresh_token(user_id: int) -> str | None:
    r = await get_redis()
    return await r.get(f"refresh_token:{user_id}")


async def delete_refresh_token(user_id: int) -> None:
    r = await get_redis()
    await r.delete(f"refresh_token:{user_id}")
