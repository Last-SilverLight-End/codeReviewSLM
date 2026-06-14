"""관리자 계정 생성 스크립트. 이미 존재하면 비밀번호 + is_admin 갱신."""
import asyncio
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.services.auth import hash_password

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")


async def main() -> None:
    if not ADMIN_PASSWORD:
        raise RuntimeError("ADMIN_PASSWORD 환경변수를 설정한 뒤 실행하세요.")

    database_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as db:
        from app.models.user import User
        result = await db.execute(select(User).where(User.email == ADMIN_EMAIL))
        user = result.scalar_one_or_none()

        if user:
            user.password_hash = hash_password(ADMIN_PASSWORD)
            user.is_admin = True
            user.is_active = True
            print(f"[UPDATE] 기존 계정 갱신: {ADMIN_EMAIL}")
        else:
            user = User(
                email=ADMIN_EMAIL,
                password_hash=hash_password(ADMIN_PASSWORD),
                auth_provider="local",
                is_active=True,
                is_admin=True,
            )
            db.add(user)
            print(f"[CREATE] 새 계정 생성: {ADMIN_EMAIL}")

        await db.commit()
        print(f"완료: 이메일 {ADMIN_EMAIL} / 관리자 True")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
