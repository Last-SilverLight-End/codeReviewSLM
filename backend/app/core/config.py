from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # PostgreSQL
    DATABASE_URL: str

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Elasticsearch
    ELASTICSEARCH_URL: str = "http://localhost:9200"
    ELASTICSEARCH_LOG_ENABLED: bool = True
    ELASTICSEARCH_LOG_INDEX_PREFIX: str = "codereview"
    ELASTICSEARCH_LOG_TIMEOUT: float = 1.0
    KIBANA_URL: str = "http://localhost:5601"

    # Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_LLM_MODEL: str = "qwen3:8b"
    OLLAMA_VISION_MODEL: str = "llava:7b"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    OLLAMA_CHAT_ENDPOINT: str = "/api/chat"
    OLLAMA_EMBED_ENDPOINT: str = "/api/embed"

    # Ollama 타임아웃 (초)
    OLLAMA_CHAT_TIMEOUT: float = 300.0
    OLLAMA_EMBED_TIMEOUT: float = 60.0
    OLLAMA_STREAM_CONNECT_TIMEOUT: float = 10.0
    OLLAMA_STREAM_WRITE_TIMEOUT: float = 30.0
    OLLAMA_STREAM_POOL_TIMEOUT: float = 10.0

    # LLM 기본 온도
    LLM_CHAT_TEMPERATURE: float = 0.3
    LLM_REVIEW_TEMPERATURE: float = 0.2
    LLM_VISION_TEMPERATURE: float = 0.1

    # 벡터 임베딩
    EMBEDDING_DIMENSION: int = 768
    STRIP_THINK_TAGS: bool = True
    HYBRID_RRF_RANK_CONSTANT: int = 60
    HYBRID_VECTOR_WEIGHT: float = 1.0
    HYBRID_ELASTICSEARCH_WEIGHT: float = 1.25

    # 무시할 디렉토리 (project_parser.py)
    IGNORE_DIRS: str | list[str] = [
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        "dist", "build", ".next", ".idea", ".vscode",
    ]

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS (쉼표 구분 문자열 → 리스트)
    CORS_ORIGINS: str | list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # 대화/채팅 제한
    CHAT_HISTORY_WINDOW: int = 20
    CONVERSATION_TITLE_MAX_LENGTH: int = 50
    LIST_CONVERSATIONS_LIMIT: int = 50
    LIST_REVIEWS_LIMIT: int = 20

    # 웹 검색
    WEB_SEARCH_MAX_WORKERS: int = 2
    WEB_RESULT_SNIPPET_MAX: int = 200

    # 파일 업로드 제한
    MAX_FILE_SIZE_BYTES: int = 500_000
    MAX_FILES_PER_PROJECT: int = 150

    @field_validator("CORS_ORIGINS", "IGNORE_DIRS", mode="before")
    @classmethod
    def _parse_str_list(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v


settings = Settings()
