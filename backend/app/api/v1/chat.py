import asyncio
import json
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import sse_events as SSE
from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_db
from app.core.deps import get_current_user
from app.models.chat import Conversation, Message
from app.models.project import Project
from app.models.user import User
from app.schemas.chat import (
    ConversationCreate,
    ConversationDetail,
    ConversationResponse,
    MessageResponse,
    ModelOptions,
    SendMessageRequest,
    SendMessageResponse,
    UpdateNoteRequest,
)
from app.services.llm import (
    _strip_think,
    answer_with_context,
    chat,
    describe_image,
    stream_chat,
    stream_multimodal_rag_chat,
    stream_vision_chat,
)
from app.services.elasticsearch_logger import schedule_log_event
from app.services.vector_store import search_chunks_by_project
from app.services.web_search import format_web_results, web_search as do_web_search

router = APIRouter(prefix="/chat", tags=["chat"])

_HISTORY_WINDOW = settings.CHAT_HISTORY_WINDOW


# ── 기존 비로그인 채팅 (호환 유지) ─────────────────────────────────────────

class _LegacyChatMessage(BaseModel):
    role: str
    content: str

class _LegacyChatRequest(BaseModel):
    messages: list[_LegacyChatMessage]
    model_options: ModelOptions = ModelOptions()

class _LegacyChatResponse(BaseModel):
    reply: str

class _ProjectQARequest(BaseModel):
    project_id: int
    question: str
    rag_top_k: int = 5
    model_options: ModelOptions = ModelOptions()


@router.post("/", response_model=_LegacyChatResponse)
async def send_message_guest(body: _LegacyChatRequest):
    """인증 없이 사용 가능한 LLM 채팅 (히스토리 미저장)."""
    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    ollama_opts = body.model_options.to_ollama_options(default_temperature=0.3)
    timeout_seconds = body.model_options.timeout_seconds(settings.OLLAMA_CHAT_TIMEOUT)
    try:
        reply, _, _ = await chat(messages, options=ollama_opts, timeout_seconds=timeout_seconds)
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Ollama 응답 시간이 초과되었습니다. 모델이 로딩 중이거나 답변 생성이 너무 오래 걸립니다.",
        ) from exc
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ollama에 연결할 수 없습니다. Ollama가 실행 중인지 확인하세요.",
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ollama 호출 실패: HTTP {exc.response.status_code}",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return _LegacyChatResponse(reply=reply)


@router.post("/project-qa", response_model=_LegacyChatResponse)
async def project_qa(
    body: _ProjectQARequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """프로젝트 RAG Q&A (히스토리 미저장)."""
    await _get_project_or_404(db, body.project_id, current_user.id)
    chunks_with_file = await search_chunks_by_project(
        db,
        project_id=body.project_id,
        user_id=current_user.id,
        query=body.question,
        top_k=body.rag_top_k,
    )
    schedule_log_event("rag-search", {
        "route": "project_qa",
        "project_id": body.project_id,
        "user_id": current_user.id,
        "query_length": len(body.question),
        "top_k": body.rag_top_k,
        "result_count": len(chunks_with_file),
        "filenames": sorted({cf.filename for cf in chunks_with_file}),
    })
    if not chunks_with_file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="관련 코드를 찾을 수 없습니다.")

    context = [
        {
            "chunk_type": cf.chunk.chunk_type,
            "name": cf.chunk.name,
            "content": cf.chunk.content,
            "start_line": cf.chunk.start_line,
            "end_line": cf.chunk.end_line,
            "filename": cf.filename,
        }
        for cf in chunks_with_file
    ]
    ollama_opts = body.model_options.to_ollama_options(default_temperature=0.3)
    timeout_seconds = body.model_options.timeout_seconds(settings.OLLAMA_CHAT_TIMEOUT)
    reply = await answer_with_context(body.question, context, options=ollama_opts, timeout_seconds=timeout_seconds)
    return _LegacyChatResponse(reply=reply)


# ── 대화 CRUD ───────────────────────────────────────────────────────────────

@router.post("/conversations", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    body: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """새 대화 시작."""
    if body.project_id is not None:
        await _get_project_or_404(db, body.project_id, current_user.id)

    conv = Conversation(
        user_id=current_user.id,
        project_id=body.project_id,
        model_name=settings.OLLAMA_LLM_MODEL,
        note=body.note,
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """내 대화 목록 (최근 50개)."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
        .limit(settings.LIST_CONVERSATIONS_LIMIT)
    )
    return result.scalars().all()


@router.get("/conversations/{conv_id}", response_model=ConversationDetail)
async def get_conversation(
    conv_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """대화 상세 — 현재 활성 브랜치의 메시지 목록 포함."""
    conv = await _get_conv_or_404(db, conv_id, current_user.id)

    # active_leaf_id에서 parent_id를 타고 루트까지 역방향 탐색
    messages = await _load_active_branch(db, conv)

    # ConversationResponse로 먼저 변환 (messages 관계 lazy load 방지)
    conv_data = ConversationResponse.model_validate(conv).model_dump()
    msg_responses = [MessageResponse.model_validate(m) for m in messages]
    return ConversationDetail(**conv_data, messages=msg_responses)


@router.delete("/conversations/{conv_id}", status_code=204)
async def delete_conversation(
    conv_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """대화 삭제 (메시지 CASCADE)."""
    conv = await _get_conv_or_404(db, conv_id, current_user.id)
    await db.delete(conv)
    await db.commit()


@router.patch("/conversations/{conv_id}/note", response_model=ConversationResponse)
async def update_conversation_note(
    conv_id: int,
    body: UpdateNoteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """대화 비고 수정."""
    conv = await _get_conv_or_404(db, conv_id, current_user.id)
    conv.note = body.note
    await db.commit()
    await db.refresh(conv)
    return conv


# ── 메시지 전송 ────────────────────────────────────────────────────────────

@router.post("/conversations/{conv_id}/messages", response_model=SendMessageResponse)
async def send_message(
    conv_id: int,
    body: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """메시지 전송 → LLM 응답 → 양쪽 저장."""
    conv = await _get_conv_or_404(db, conv_id, current_user.id)

    # 분기점: parent_id 지정 없으면 현재 active_leaf 이어붙임
    parent_id = body.parent_id if body.parent_id is not None else conv.active_leaf_id

    # user 메시지 저장
    user_msg = Message(
        conversation_id=conv_id,
        parent_id=parent_id,
        role="user",
        content=body.content,
    )
    db.add(user_msg)
    await db.flush()

    # 대화 제목: 첫 메시지로 자동 생성
    if conv.message_count == 0:
        conv.title = body.content[:settings.CONVERSATION_TITLE_MAX_LENGTH]

    # 멀티턴 컨텍스트 구성 (슬라이딩 윈도우 20개)
    history = await _load_active_branch(db, conv)
    history_msgs = [{"role": m.role, "content": m.content} for m in history]
    history_msgs.append({"role": "user", "content": body.content})
    context_window = history_msgs[-_HISTORY_WINDOW:]

    # LLM 호출
    ollama_opts = body.model_options.to_ollama_options(default_temperature=0.3)
    timeout_seconds = body.model_options.timeout_seconds(settings.OLLAMA_CHAT_TIMEOUT)
    reply, tokens_in, tokens_out = await chat(context_window, options=ollama_opts, timeout_seconds=timeout_seconds)

    # assistant 메시지 저장
    asst_msg = Message(
        conversation_id=conv_id,
        parent_id=user_msg.id,
        role="assistant",
        content=reply,
        tokens_input=tokens_in,
        tokens_output=tokens_out,
    )
    db.add(asst_msg)
    await db.flush()

    # 대화 상태 업데이트
    conv.active_leaf_id = asst_msg.id
    conv.message_count += 2
    await db.commit()
    await db.refresh(user_msg)
    await db.refresh(asst_msg)

    return SendMessageResponse(user_message=user_msg, assistant_message=asst_msg)


@router.post("/conversations/{conv_id}/messages/stream")
async def send_message_stream(
    conv_id: int,
    body: SendMessageRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """메시지 전송 → LLM 스트리밍 응답 (SSE)."""
    conv = await _get_conv_or_404(db, conv_id, current_user.id)
    parent_id = body.parent_id if body.parent_id is not None else conv.active_leaf_id
    is_first_msg = conv.message_count == 0
    project_id = body.project_id if body.project_id is not None else conv.project_id
    if project_id is not None:
        await _get_project_or_404(db, project_id, current_user.id)

    history = await _load_active_branch(db, conv)
    history_msgs = [{"role": m.role, "content": m.content} for m in history]
    history_msgs.append({"role": "user", "content": body.content})
    context_window = history_msgs[-_HISTORY_WINDOW:]

    async def event_generator():
        nonlocal context_window
        full_reply = ""
        tokens_in = 0
        tokens_out = 0

        # 첫 토큰까지 시간이 걸리므로 keep-alive ping 먼저 전송
        yield ": ping\n\n"

        image_b64 = body.image_b64
        # 3-way 분기
        # (1) 이미지 + 프로젝트 → 멀티모달 RAG
        # (2) 이미지만 → 비전 모델 직접 스트리밍
        # (3) 텍스트만 → 일반 스트리밍
        think_mode = body.think_mode
        use_web = body.web_search
        ollama_opts = body.model_options.to_ollama_options(default_temperature=0.3)
        rag_top_k = body.rag_top_k
        web_max_results = body.web_max_results

        # ── 웹 검색 ─────────────────────────────────────────────────────────
        if use_web:
            yield f"data: {json.dumps({SSE.STATUS: '🌐 웹 검색 중...'}, ensure_ascii=False)}\n\n"
            web_results = await do_web_search(body.content, max_results=web_max_results)
            schedule_log_event("web-search", {
                "route": "message_stream",
                "conversation_id": conv_id,
                "user_id": current_user.id,
                "query_length": len(body.content),
                "max_results": web_max_results,
                "result_count": len(web_results),
            })
            if web_results:
                web_refs = [{"title": r["title"], "url": r["url"], "snippet": r["snippet"][:settings.WEB_RESULT_SNIPPET_MAX]} for r in web_results]
                yield f"data: {json.dumps({SSE.WEB_REFS: web_refs}, ensure_ascii=False)}\n\n"
                # 검색 결과를 마지막 user 메시지에 주입
                web_ctx = "\n\n[웹 검색 결과]\n" + format_web_results(web_results) + "\n\n위 결과를 참고해 답변하세요."
                if context_window and context_window[-1]["role"] == "user":
                    context_window = context_window[:-1] + [
                        {"role": "user", "content": context_window[-1]["content"] + web_ctx}
                    ]

        # ── 멀티모달 RAG / 비전 / 일반 채팅 분기 ─────────────────────────────
        if image_b64 and project_id:
            yield f"data: {json.dumps({SSE.STATUS: '이미지 분석 중...'}, ensure_ascii=False)}\n\n"
            try:
                image_description = await describe_image(image_b64, body.content)
            except Exception as e:
                yield f"data: {json.dumps({SSE.ERROR: f'이미지 분석 실패: {str(e)}'})}\n\n"
                return

            yield f"data: {json.dumps({SSE.STATUS: '관련 코드 검색 중...'}, ensure_ascii=False)}\n\n"
            try:
                async with AsyncSessionLocal() as search_db:
                    chunks_with_file = await search_chunks_by_project(
                        search_db,
                        project_id=project_id,
                        user_id=current_user.id,
                        query=image_description,
                        top_k=rag_top_k,
                    )
                code_chunks = [
                    {
                        "chunk_type": cf.chunk.chunk_type,
                        "name": cf.chunk.name,
                        "content": cf.chunk.content,
                        "start_line": cf.chunk.start_line,
                        "end_line": cf.chunk.end_line,
                        "filename": cf.filename,
                    }
                    for cf in chunks_with_file
                ]
                if chunks_with_file:
                    rag_refs = [
                        {"filename": cf.filename, "chunk_type": cf.chunk.chunk_type,
                         "name": cf.chunk.name or "anonymous",
                         "start_line": cf.chunk.start_line, "end_line": cf.chunk.end_line}
                        for cf in chunks_with_file
                    ]
                    yield f"data: {json.dumps({SSE.RAG_REFS: rag_refs}, ensure_ascii=False)}\n\n"
                schedule_log_event("rag-search", {
                    "route": "message_stream_multimodal",
                    "conversation_id": conv_id,
                    "project_id": project_id,
                    "user_id": current_user.id,
                    "query_source": "image_description",
                    "query_length": len(image_description),
                    "top_k": rag_top_k,
                    "result_count": len(chunks_with_file),
                    "filenames": sorted({cf.filename for cf in chunks_with_file}),
                })
                if not chunks_with_file:
                    yield f"data: {json.dumps({SSE.ERROR: '관련 코드를 찾을 수 없습니다.'}, ensure_ascii=False)}\n\n"
                    return
            except Exception as e:
                yield f"data: {json.dumps({SSE.ERROR: f'관련 코드 검색 실패: {str(e)}'}, ensure_ascii=False)}\n\n"
                return

            yield f"data: {json.dumps({SSE.STATUS: '답변 생성 중...'}, ensure_ascii=False)}\n\n"
            stream_fn = stream_multimodal_rag_chat(context_window, image_description, code_chunks, think_mode, ollama_opts)

        elif image_b64:
            stream_fn = stream_vision_chat(context_window, image_b64, think_mode, ollama_opts)
        else:
            # 프로젝트 컨텍스트가 있는 일반 텍스트 채팅 — hybrid 검색 (웹검색과 동시 가능)
            if project_id:
                try:
                    async with AsyncSessionLocal() as search_db:
                        chunks_with_file = await search_chunks_by_project(
                            search_db,
                            project_id=project_id,
                            user_id=current_user.id,
                            query=body.content,
                            top_k=rag_top_k,
                        )
                    if chunks_with_file:
                        rag_refs = [
                            {"filename": cf.filename, "chunk_type": cf.chunk.chunk_type,
                             "name": cf.chunk.name or "anonymous",
                             "start_line": cf.chunk.start_line, "end_line": cf.chunk.end_line}
                            for cf in chunks_with_file
                        ]
                        yield f"data: {json.dumps({SSE.RAG_REFS: rag_refs}, ensure_ascii=False)}\n\n"
                        code_ctx = "\n\n[관련 코드]\n" + "\n\n".join(
                            f"[{cf.filename} | {cf.chunk.chunk_type} {cf.chunk.name or ''}]\n{cf.chunk.content}"
                            for cf in chunks_with_file
                        )
                        if context_window and context_window[-1]["role"] == "user":
                            context_window = context_window[:-1] + [
                                {"role": "user", "content": context_window[-1]["content"] + code_ctx}
                            ]
                    schedule_log_event("rag-search", {
                        "route": "message_stream",
                        "conversation_id": conv_id,
                        "project_id": project_id,
                        "user_id": current_user.id,
                        "query_source": "message",
                        "query_length": len(body.content),
                        "top_k": rag_top_k,
                        "result_count": len(chunks_with_file),
                        "filenames": sorted({cf.filename for cf in chunks_with_file}),
                    })
                    if not chunks_with_file:
                        yield f"data: {json.dumps({SSE.ERROR: '관련 코드를 찾을 수 없습니다.'}, ensure_ascii=False)}\n\n"
                        return
                except Exception as e:
                    yield f"data: {json.dumps({SSE.ERROR: f'관련 코드 검색 실패: {str(e)}'}, ensure_ascii=False)}\n\n"
                    return
            stream_fn = stream_chat(context_window, think_mode, ollama_opts)

        # <think> 토큰 파싱 상태
        in_think = False

        try:
            async for token, done, t_in, t_out in stream_fn:
                if await request.is_disconnected():
                    return
                if done:
                    tokens_in, tokens_out = t_in, t_out
                elif token:
                    full_reply += token

                    # think 태그 구간 감지 및 분리
                    if "<think>" in token:
                        in_think = True
                    if in_think:
                        yield f"data: {json.dumps({SSE.THINK: token}, ensure_ascii=False)}\n\n"
                        if "</think>" in token:
                            in_think = False
                    else:
                        yield f"data: {json.dumps({SSE.TOKEN: token}, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            return
        except Exception as e:
            yield f"data: {json.dumps({SSE.ERROR: str(e)})}\n\n"
            return

        if not full_reply:
            yield f"data: {json.dumps({SSE.ERROR: '응답이 비어있습니다.'})}\n\n"
            return

        # 스트리밍 완료 후 새 세션으로 저장
        try:
            async with AsyncSessionLocal() as save_db:
                user_msg = Message(
                    conversation_id=conv_id,
                    parent_id=parent_id,
                    role="user",
                    content=body.content,
                )
                save_db.add(user_msg)
                await save_db.flush()

                clean_reply = _strip_think(full_reply)
                asst_msg = Message(
                    conversation_id=conv_id,
                    parent_id=user_msg.id,
                    role="assistant",
                    content=clean_reply,
                    tokens_input=tokens_in,
                    tokens_output=tokens_out,
                )
                save_db.add(asst_msg)
                await save_db.flush()

                from sqlalchemy import update
                await save_db.execute(
                    update(Conversation)
                    .where(Conversation.id == conv_id)
                    .values(
                        active_leaf_id=asst_msg.id,
                        message_count=Conversation.message_count + 2,
                        **({"title": body.content[:settings.CONVERSATION_TITLE_MAX_LENGTH]} if is_first_msg else {}),
                    )
                )
                await save_db.commit()
                msg_id = asst_msg.id
        except Exception as e:
            yield f"data: {json.dumps({SSE.ERROR: f'DB 저장 실패: {str(e)}'})}\n\n"
            return

        yield f"data: {json.dumps({SSE.DONE: True, 'message_id': msg_id})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/conversations/{conv_id}/messages/{msg_id}", status_code=204)
async def delete_message(
    conv_id: int,
    msg_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """메시지 소프트 삭제."""
    await _get_conv_or_404(db, conv_id, current_user.id)
    msg = await db.get(Message, msg_id)
    if not msg or msg.conversation_id != conv_id:
        raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다.")
    msg.deleted_at = datetime.now(timezone.utc)
    await db.commit()


@router.patch("/conversations/{conv_id}/messages/{msg_id}/note", response_model=None)
async def update_message_note(
    conv_id: int,
    msg_id: int,
    body: UpdateNoteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """메시지 비고 수정."""
    await _get_conv_or_404(db, conv_id, current_user.id)
    msg = await db.get(Message, msg_id)
    if not msg or msg.conversation_id != conv_id:
        raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다.")
    msg.note = body.note
    await db.commit()


# ── 응답 재생성 ────────────────────────────────────────────────────────────

class _RegenerateRequest(BaseModel):
    model_options: ModelOptions = ModelOptions()


@router.post("/conversations/{conv_id}/messages/{msg_id}/regenerate", response_model=SendMessageResponse)
async def regenerate_message(
    conv_id: int,
    msg_id: int,
    body: _RegenerateRequest = _RegenerateRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """assistant 메시지 재생성 — 기존 응답 소프트 삭제 후 새 응답 생성."""
    conv = await _get_conv_or_404(db, conv_id, current_user.id)
    old_asst = await db.get(Message, msg_id)
    if not old_asst or old_asst.conversation_id != conv_id or old_asst.role != "assistant":
        raise HTTPException(status_code=404, detail="재생성할 assistant 메시지를 찾을 수 없습니다.")

    # 기존 응답 소프트 삭제
    old_asst.deleted_at = datetime.now(timezone.utc)

    # 부모(user 메시지)까지의 히스토리 구성
    user_msg = await db.get(Message, old_asst.parent_id)
    if not user_msg:
        raise HTTPException(status_code=400, detail="원본 user 메시지를 찾을 수 없습니다.")

    history = await _build_branch_to(db, user_msg)
    context_window = [{"role": m.role, "content": m.content} for m in history][-_HISTORY_WINDOW:]

    ollama_opts = body.model_options.to_ollama_options(default_temperature=0.3)
    timeout_seconds = body.model_options.timeout_seconds(settings.OLLAMA_CHAT_TIMEOUT)
    reply, tokens_in, tokens_out = await chat(context_window, options=ollama_opts, timeout_seconds=timeout_seconds)

    new_asst = Message(
        conversation_id=conv_id,
        parent_id=user_msg.id,
        role="assistant",
        content=reply,
        tokens_input=tokens_in,
        tokens_output=tokens_out,
        is_regenerated=True,
    )
    db.add(new_asst)
    await db.flush()

    conv.active_leaf_id = new_asst.id
    await db.commit()
    await db.refresh(user_msg)
    await db.refresh(new_asst)

    return SendMessageResponse(user_message=user_msg, assistant_message=new_asst)


# ── 형제 메시지 (브랜치 탐색) ──────────────────────────────────────────────

@router.get("/conversations/{conv_id}/messages/{msg_id}/siblings")
async def get_siblings(
    conv_id: int,
    msg_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """같은 parent를 공유하는 형제 메시지 목록 (ChatGPT '2/3' 표시용)."""
    await _get_conv_or_404(db, conv_id, current_user.id)
    msg = await db.get(Message, msg_id)
    if not msg or msg.conversation_id != conv_id:
        raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다.")

    result = await db.execute(
        select(Message)
        .where(Message.parent_id == msg.parent_id, Message.conversation_id == conv_id)
        .order_by(Message.created_at)
    )
    siblings = result.scalars().all()
    return {"siblings": [{"id": s.id, "created_at": s.created_at} for s in siblings]}


# ── 헬퍼 ──────────────────────────────────────────────────────────────────

async def _get_conv_or_404(db: AsyncSession, conv_id: int, user_id: int) -> Conversation:
    conv = await db.get(Conversation, conv_id)
    if not conv or conv.user_id != user_id:
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")
    return conv


async def _get_project_or_404(db: AsyncSession, project_id: int, user_id: int) -> Project:
    project = await db.get(Project, project_id)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    return project


async def _load_active_branch(db: AsyncSession, conv: Conversation) -> list:
    """active_leaf_id → parent_id 체인을 역방향 탐색해 순서대로 반환."""
    if conv.active_leaf_id is None:
        return []
    return await _build_branch_to(db, await db.get(Message, conv.active_leaf_id))


async def _build_branch_to(db: AsyncSession, leaf: Message | None) -> list:
    """leaf에서 루트까지 parent_id 체인 탐색 후 시간순 정렬 반환."""
    if leaf is None:
        return []
    chain: list[Message] = []
    current = leaf
    visited: set[int] = set()
    while current is not None and current.id not in visited:
        if current.deleted_at is None:
            chain.append(current)
        visited.add(current.id)
        if current.parent_id is None:
            break
        current = await db.get(Message, current.parent_id)
    chain.reverse()
    return chain
