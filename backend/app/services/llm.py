import json
import logging
import re
import time
from collections.abc import AsyncGenerator

import httpx

from app.core.config import settings
from app.services.elasticsearch_logger import schedule_log_event

_log = logging.getLogger("app.llm")

_THINK_TAG = re.compile(r"<think>.*?</think>", re.DOTALL)
_OLLAMA_CHAT_URL = f"{settings.OLLAMA_BASE_URL}{settings.OLLAMA_CHAT_ENDPOINT}"


def _strip_think(content: str) -> str:
    if settings.STRIP_THINK_TAGS:
        return _THINK_TAG.sub("", content).strip()
    return content.strip()


def _content_or_raise(body: dict, purpose: str) -> str:
    message = body.get("message", {})
    content = message.get("content") or ""
    cleaned = _strip_think(content)
    if cleaned:
        return cleaned

    thinking = message.get("thinking") or ""
    if thinking:
        raise RuntimeError(
            f"{purpose}: 모델이 최종 답변 없이 thinking만 반환했습니다. "
            "num_predict를 늘리거나 think 옵션을 비활성화해야 합니다."
        )
    raise RuntimeError(f"{purpose}: 모델 응답이 비어있습니다.")


# ── 타임아웃 상수 ─────────────────────────────────────────────────────────────
def _chat_timeout(timeout_seconds: float | None = None) -> httpx.Timeout:
    return httpx.Timeout(timeout_seconds or settings.OLLAMA_CHAT_TIMEOUT)

def _stream_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        connect=settings.OLLAMA_STREAM_CONNECT_TIMEOUT,
        read=None,
        write=settings.OLLAMA_STREAM_WRITE_TIMEOUT,
        pool=settings.OLLAMA_STREAM_POOL_TIMEOUT,
    )

_REVIEW_PROMPT = """/no_think
당신은 코드 리뷰 전문가입니다. `{filename}` 파일의 코드를 리뷰하세요.

{code_sections}

**중요 규칙:**
- 위 코드에 실제로 존재하는 내용만 작성하세요. 코드에 없는 내용은 절대 작성하지 마세요.
- 버그를 보고할 때는 반드시 해당 줄의 코드를 그대로 인용하세요.

반드시 한국어로, 아래 구조에 맞게 마크다운으로 답변하세요:

## 요약
코드가 무엇을 하는지, 전반적인 품질을 한 문단으로 설명하세요.

## 문제점
코드에 실제로 존재하는 버그만 작성하세요. 없으면 "심각한 문제 없음"으로 작성.
각 버그는 반드시 아래 형식으로 작성하세요:

- **줄 N**: `실제 코드 그대로 인용` → 문제 설명

## 코드 품질
네이밍, 가독성, 구조, 유지보수성 관련 의견.

## 성능
성능 관련 우려 사항. 없으면 "특별한 성능 문제 없음"으로 작성.

## 보안
보안 취약점. 없으면 "보안 문제 없음"으로 작성.

## 개선 제안
구체적인 개선 방법을 번호 목록으로 작성하세요.
"""


def _format_chunks(chunks: list[dict]) -> str:
    parts = []
    for c in chunks:
        label = f"[{c['chunk_type'].upper()}: {c['name'] or 'anonymous'} | line {c['start_line']}-{c['end_line']}]"
        lines = c["content"].split("\n")
        numbered = "\n".join(
            f"{c['start_line'] + i:4d} | {line}" for i, line in enumerate(lines)
        )
        parts.append(f"{label}\n```\n{numbered}\n```")
    return "\n\n".join(parts)


_SYSTEM_PROMPT_BASE = """당신은 코드 리뷰 전문 AI 어시스턴트입니다. 다음을 도와드릴 수 있습니다:
- 코드, 알고리즘, 프로그래밍 개념 질문 답변
- 코드의 버그, 품질, 성능, 보안 리뷰
- 코드 동작 설명 및 개선 제안
- 디버깅 지원

반드시 한국어로 답변하세요. 코드 블록에는 마크다운을 사용하세요.
"""

# 하위 호환 — 비스트리밍 chat() 함수용 (항상 no_think)
_SYSTEM_PROMPT = "/no_think\n" + _SYSTEM_PROMPT_BASE


def _build_system(base: str, think_mode: bool) -> str:
    return base if think_mode else "/no_think\n" + base


async def chat(
    messages: list[dict],
    options: dict | None = None,
    timeout_seconds: float | None = None,
) -> tuple[str, int, int]:
    """일반 대화. (reply, tokens_input, tokens_output) 튜플 반환."""
    payload = [{"role": "system", "content": _SYSTEM_PROMPT}] + messages
    start = time.monotonic()
    async with httpx.AsyncClient(timeout=_chat_timeout(timeout_seconds)) as client:
        response = await client.post(
            _OLLAMA_CHAT_URL,
            json={
                "model": settings.OLLAMA_LLM_MODEL,
                "messages": payload,
                "stream": False,
                "think": False,
                "options": options or {"temperature": settings.LLM_CHAT_TEMPERATURE},
            },
        )
        response.raise_for_status()
        body = response.json()
        tokens_in = body.get("prompt_eval_count", 0)
        tokens_out = body.get("eval_count", 0)
    schedule_log_event("llm-call", {
        "purpose": "chat",
        "model": settings.OLLAMA_LLM_MODEL,
        "stream": False,
        "message_count": len(messages),
        "tokens_input": tokens_in,
        "tokens_output": tokens_out,
        "duration_ms": int((time.monotonic() - start) * 1000),
    })
    return _content_or_raise(body, "chat"), tokens_in, tokens_out


async def stream_vision_chat(
    messages: list[dict],
    image_b64: str,
    think_mode: bool = False,
    options: dict | None = None,
) -> AsyncGenerator[tuple[str, bool, int, int], None]:
    """이미지 포함 스트리밍. 마지막 user 메시지에 이미지 첨부."""
    payload = list(messages)
    if payload and payload[-1]["role"] == "user":
        payload[-1] = {**payload[-1], "images": [image_b64]}
    # vision 모델에 think 제어 적용 (지원 모델에 한해)
    if not think_mode and payload and payload[0].get("role") != "system":
        payload = [{"role": "system", "content": "/no_think"}] + payload

    async with httpx.AsyncClient(timeout=_stream_timeout()) as client:
        async with client.stream(
            "POST",
            _OLLAMA_CHAT_URL,
            json={
                "model": settings.OLLAMA_VISION_MODEL,
                "messages": payload,
                "stream": True,
                "think": bool(think_mode),
                "options": options or {"temperature": settings.LLM_VISION_TEMPERATURE},
            },
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                data = json.loads(line)
                token = data.get("message", {}).get("content", "")
                done = data.get("done", False)
                if done:
                    yield "", True, data.get("prompt_eval_count", 0), data.get("eval_count", 0)
                elif token:
                    yield token, False, 0, 0


async def stream_chat(
    messages: list[dict],
    think_mode: bool = False,
    options: dict | None = None,
) -> AsyncGenerator[tuple[str, bool, int, int], None]:
    """스트리밍 채팅. yield (token, done, tokens_in, tokens_out)"""
    payload = [{"role": "system", "content": _build_system(_SYSTEM_PROMPT_BASE, think_mode)}] + messages
    start = time.monotonic()
    async with httpx.AsyncClient(timeout=_stream_timeout()) as client:
        async with client.stream(
            "POST",
            _OLLAMA_CHAT_URL,
            json={
                "model": settings.OLLAMA_LLM_MODEL,
                "messages": payload,
                "stream": True,
                "think": bool(think_mode),
                "options": options or {"temperature": settings.LLM_CHAT_TEMPERATURE},
            },
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                data = json.loads(line)
                token = data.get("message", {}).get("content", "")
                done = data.get("done", False)
                if done:
                    schedule_log_event("llm-call", {
                        "purpose": "stream_chat",
                        "model": settings.OLLAMA_LLM_MODEL,
                        "stream": True,
                        "think_mode": think_mode,
                        "message_count": len(messages),
                        "tokens_input": data.get("prompt_eval_count", 0),
                        "tokens_output": data.get("eval_count", 0),
                        "duration_ms": int((time.monotonic() - start) * 1000),
                    })
                    yield "", True, data.get("prompt_eval_count", 0), data.get("eval_count", 0)
                elif token:
                    yield token, False, 0, 0


_RAG_SYSTEM = """/no_think
당신은 코드 전문 AI 어시스턴트입니다. 사용자가 업로드한 프로젝트 코드베이스에 대한 질문에 답변합니다.
제공된 코드 컨텍스트를 기반으로 답변하세요. 컨텍스트에 정보가 부족하면 솔직하게 말씀해 주세요.
반드시 한국어로 답변하세요. 마크다운을 사용하세요.
"""


async def answer_with_context(
    question: str,
    context_chunks: list[dict],
    options: dict | None = None,
    timeout_seconds: float | None = None,
) -> str:
    """RAG 기반 프로젝트 Q&A — 검색된 코드 청크를 컨텍스트로 LLM에 전달."""
    context_text = _format_chunks(context_chunks)
    user_content = f"""## 관련 코드\n\n{context_text}\n\n## 질문\n\n{question}"""
    start = time.monotonic()

    async with httpx.AsyncClient(timeout=_chat_timeout(timeout_seconds)) as client:
        response = await client.post(
            _OLLAMA_CHAT_URL,
            json={
                "model": settings.OLLAMA_LLM_MODEL,
                "messages": [
                    {"role": "system", "content": _RAG_SYSTEM},
                    {"role": "user", "content": user_content},
                ],
                "stream": False,
                "think": False,
                "options": options or {"temperature": settings.LLM_CHAT_TEMPERATURE},
            },
        )
        response.raise_for_status()
        body = response.json()
    schedule_log_event("llm-call", {
        "purpose": "answer_with_context",
        "model": settings.OLLAMA_LLM_MODEL,
        "stream": False,
        "question_length": len(question),
        "context_chunk_count": len(context_chunks),
        "duration_ms": int((time.monotonic() - start) * 1000),
        "tokens_input": body.get("prompt_eval_count", 0),
        "tokens_output": body.get("eval_count", 0),
    })
    return _content_or_raise(body, "answer_with_context")


_MULTIMODAL_RAG_SYSTEM_BASE = """당신은 코드 전문 AI 어시스턴트입니다. 사용자가 업로드한 이미지와 관련 코드베이스를 함께 분석합니다.
제공된 이미지 분석 내용과 코드 컨텍스트를 바탕으로 정확하게 답변하세요.
반드시 한국어로 답변하세요. 마크다운을 사용하세요.
"""


async def describe_image(image_b64: str, question: str, options: dict | None = None) -> str:
    """llava 모델로 이미지를 텍스트 설명으로 변환 (비스트리밍)."""
    _log.info(f"[describe_image] 시작 — 모델: {settings.OLLAMA_VISION_MODEL}")
    start = time.monotonic()
    async with httpx.AsyncClient(timeout=_stream_timeout()) as client:
        response = await client.post(
            _OLLAMA_CHAT_URL,
            json={
                "model": settings.OLLAMA_VISION_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "이미지를 상세히 분석하세요. "
                            "에러 메시지, UI 상태, 스택 트레이스, 코드 스니펫, 텍스트를 빠짐없이 정확히 기술하세요. "
                            f"질문 맥락: {question}"
                        ),
                        "images": [image_b64],
                    }
                ],
                "stream": False,
                "think": False,
                "options": options or {"temperature": settings.LLM_VISION_TEMPERATURE},
            },
        )
        response.raise_for_status()
        body = response.json()
    result = _content_or_raise(body, "describe_image")
    schedule_log_event("llm-call", {
        "purpose": "describe_image",
        "model": settings.OLLAMA_VISION_MODEL,
        "stream": False,
        "question_length": len(question),
        "image_b64_length": len(image_b64),
        "description_length": len(result),
        "duration_ms": int((time.monotonic() - start) * 1000),
        "tokens_input": body.get("prompt_eval_count", 0),
        "tokens_output": body.get("eval_count", 0),
    })
    _log.info(f"[describe_image] 완료 — {len(result)}자 설명 생성")
    return result


async def stream_multimodal_rag_chat(
    messages: list[dict],
    image_description: str,
    code_chunks: list[dict],
    think_mode: bool = False,
    options: dict | None = None,
) -> AsyncGenerator[tuple[str, bool, int, int], None]:
    """이미지 설명 + 코드 청크를 컨텍스트로 주입해 qwen3로 스트리밍."""
    _log.info(f"[multimodal_rag] 시작 — 코드청크: {len(code_chunks)}개, 모델: {settings.OLLAMA_LLM_MODEL}")
    start = time.monotonic()
    augmented = list(messages[:-1])
    last_content = messages[-1]["content"] if messages else ""

    injected = f"[이미지 분석 결과]\n{image_description}"
    if code_chunks:
        injected += f"\n\n[관련 코드]\n{_format_chunks(code_chunks)}"
    injected += f"\n\n[질문]\n{last_content}"

    augmented.append({"role": "user", "content": injected})
    payload = [{"role": "system", "content": _build_system(_MULTIMODAL_RAG_SYSTEM_BASE, think_mode)}] + augmented

    async with httpx.AsyncClient(timeout=_stream_timeout()) as client:
        async with client.stream(
            "POST",
            _OLLAMA_CHAT_URL,
            json={
                "model": settings.OLLAMA_LLM_MODEL,
                "messages": payload,
                "stream": True,
                "think": bool(think_mode),
                "options": options or {"temperature": settings.LLM_CHAT_TEMPERATURE},
            },
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                data = json.loads(line)
                token = data.get("message", {}).get("content", "")
                done = data.get("done", False)
                if done:
                    _log.info(f"[multimodal_rag] 완료 — in:{data.get('prompt_eval_count',0)} out:{data.get('eval_count',0)} tokens")
                    schedule_log_event("llm-call", {
                        "purpose": "stream_multimodal_rag",
                        "model": settings.OLLAMA_LLM_MODEL,
                        "stream": True,
                        "think_mode": think_mode,
                        "message_count": len(messages),
                        "context_chunk_count": len(code_chunks),
                        "image_description_length": len(image_description),
                        "tokens_input": data.get("prompt_eval_count", 0),
                        "tokens_output": data.get("eval_count", 0),
                        "duration_ms": int((time.monotonic() - start) * 1000),
                    })
                    yield "", True, data.get("prompt_eval_count", 0), data.get("eval_count", 0)
                elif token:
                    yield token, False, 0, 0


async def generate_review(chunks: list[dict], filename: str, options: dict | None = None) -> str:
    """qwen3:8b로 코드 리뷰를 생성하고 thinking 태그를 제거한 결과를 반환."""
    code_sections = _format_chunks(chunks)
    prompt = _REVIEW_PROMPT.format(filename=filename, code_sections=code_sections)
    start = time.monotonic()

    async with httpx.AsyncClient(timeout=_chat_timeout()) as client:
        response = await client.post(
            _OLLAMA_CHAT_URL,
            json={
                "model": settings.OLLAMA_LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "think": False,
                "options": options or {"temperature": settings.LLM_REVIEW_TEMPERATURE},
            },
        )
        response.raise_for_status()
        body = response.json()

    schedule_log_event("llm-call", {
        "purpose": "generate_review",
        "model": settings.OLLAMA_LLM_MODEL,
        "stream": False,
        "filename": filename,
        "context_chunk_count": len(chunks),
        "tokens_input": body.get("prompt_eval_count", 0),
        "tokens_output": body.get("eval_count", 0),
        "duration_ms": int((time.monotonic() - start) * 1000),
    })
    return _content_or_raise(body, "generate_review")
