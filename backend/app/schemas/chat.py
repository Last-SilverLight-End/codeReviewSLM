from datetime import datetime

from pydantic import BaseModel


# ── 메시지 ──────────────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    parent_id: int | None
    role: str
    content: str
    tokens_input: int | None
    tokens_output: int | None
    is_regenerated: bool
    deleted_at: datetime | None
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── 대화 ──────────────────────────────────────────────────────────────────

class ConversationResponse(BaseModel):
    id: int
    user_id: int
    project_id: int | None
    model_name: str
    title: str
    message_count: int
    active_leaf_id: int | None
    note: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetail(ConversationResponse):
    messages: list[MessageResponse] = []


# ── 요청 ──────────────────────────────────────────────────────────────────

class ConversationCreate(BaseModel):
    project_id: int | None = None
    note: str | None = None


class ModelOptions(BaseModel):
    """Ollama API options — None 값은 Ollama 기본값 사용."""
    # 샘플링
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    min_p: float | None = None
    seed: int | None = None
    # 반복 제어
    repeat_penalty: float | None = None
    repeat_last_n: int | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    # 생성 길이
    num_predict: int | None = None
    num_ctx: int | None = None
    # 하드웨어
    num_gpu: int | None = None
    low_vram: bool | None = None
    f16_kv: bool | None = None
    # 애플리케이션 요청 제한. Ollama options에는 전달하지 않는다.
    request_timeout_seconds: float | None = None

    def to_ollama_options(self, default_temperature: float = 0.3) -> dict:
        """None 제외 후 Ollama options dict 반환."""
        d: dict = {"temperature": default_temperature}
        for field, val in self.model_dump().items():
            if field != "request_timeout_seconds" and val is not None:
                d[field] = val
        return d

    def timeout_seconds(self, default: float) -> float:
        """UI에서 받은 요청 제한 시간을 안전한 범위로 보정한다."""
        if self.request_timeout_seconds is None:
            return default
        return min(max(float(self.request_timeout_seconds), 10.0), 900.0)


class SendMessageRequest(BaseModel):
    content: str
    parent_id: int | None = None
    image_b64: str | None = None
    project_id: int | None = None
    think_mode: bool = False
    web_search: bool = False
    model_options: ModelOptions = ModelOptions()
    rag_top_k: int = 5
    web_max_results: int = 5


class SendMessageResponse(BaseModel):
    user_message: MessageResponse
    assistant_message: MessageResponse


class UpdateNoteRequest(BaseModel):
    note: str | None = None
