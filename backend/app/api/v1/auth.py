from fastapi import APIRouter, Depends, HTTPException, status
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, UserResponse
from app.services import auth as auth_svc
from app.services.redis import delete_refresh_token, get_refresh_token, set_refresh_token
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(User).where(User.email == body.email))
    except (SQLAlchemyError, OSError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="데이터베이스에 연결할 수 없습니다. PostgreSQL 컨테이너가 실행 중인지 확인하세요.") from exc
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 사용 중인 이메일입니다.")

    user = User(
        email=body.email,
        password_hash=auth_svc.hash_password(body.password),
        auth_provider="local",
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except (SQLAlchemyError, OSError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="데이터베이스에 연결할 수 없습니다. PostgreSQL 컨테이너가 실행 중인지 확인하세요.") from exc
    return user


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(User).where(User.email == body.email))
    except (SQLAlchemyError, OSError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="데이터베이스에 연결할 수 없습니다. PostgreSQL 컨테이너가 실행 중인지 확인하세요.") from exc
    user = result.scalar_one_or_none()

    if not user or not user.password_hash or not auth_svc.verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="이메일 또는 비밀번호가 올바르지 않습니다.")

    access_token = auth_svc.create_access_token(user.id)
    refresh_token = auth_svc.create_refresh_token(user.id)
    try:
        await set_refresh_token(user.id, refresh_token, settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    except RedisError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redis에 연결할 수 없습니다. Redis 컨테이너가 실행 중인지 확인하세요.") from exc

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(current_user: User = Depends(get_current_user)):
    await delete_refresh_token(current_user.id)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = auth_svc.decode_token(body.refresh_token)
    user_id = payload.get("sub")
    token_type = payload.get("type")

    if not user_id or token_type != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 Refresh Token입니다.")

    try:
        stored = await get_refresh_token(int(user_id))
    except RedisError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redis에 연결할 수 없습니다. Redis 컨테이너가 실행 중인지 확인하세요.") from exc
    if stored != body.refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="만료되었거나 유효하지 않은 Refresh Token입니다.")

    try:
        result = await db.execute(select(User).where(User.id == int(user_id)))
    except (SQLAlchemyError, OSError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="데이터베이스에 연결할 수 없습니다. PostgreSQL 컨테이너가 실행 중인지 확인하세요.") from exc
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="사용자를 찾을 수 없습니다.")

    new_access = auth_svc.create_access_token(user.id)
    new_refresh = auth_svc.create_refresh_token(user.id)
    try:
        await set_refresh_token(user.id, new_refresh, settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    except RedisError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redis에 연결할 수 없습니다. Redis 컨테이너가 실행 중인지 확인하세요.") from exc

    return TokenResponse(access_token=new_access, refresh_token=new_refresh)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user
