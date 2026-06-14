import asyncio
import logging
from collections import deque
from datetime import datetime, timezone


class LogEntry:
    __slots__ = ("ts", "level", "source", "message")

    def __init__(self, level: str, source: str, message: str):
        self.ts = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        self.level = level
        self.source = source
        self.message = message

    def to_dict(self) -> dict:
        return {"ts": self.ts, "level": self.level, "source": self.source, "msg": self.message}


class LogStore:
    def __init__(self, maxlen: int = 500):
        self._history: deque[LogEntry] = deque(maxlen=maxlen)
        self._subscribers: list[asyncio.Queue] = []

    def add(self, level: str, source: str, message: str) -> None:
        entry = LogEntry(level, source, message)
        self._history.append(entry)
        for q in self._subscribers:
            try:
                q.put_nowait(entry)
            except asyncio.QueueFull:
                pass

    def history(self) -> list[LogEntry]:
        return list(self._history)

    def clear(self) -> None:
        self._history.clear()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass


log_store = LogStore()


# Python logging → log_store 연결
class _LogStoreHandler(logging.Handler):
    _SOURCE_MAP = {
        "uvicorn.access": "HTTP",
        "uvicorn.error": "UVICORN",
        "uvicorn": "UVICORN",
        "fastapi": "FASTAPI",
        "sqlalchemy.engine": "SQL",
        "app": "APP",
    }

    def emit(self, record: logging.LogRecord) -> None:
        source = self._SOURCE_MAP.get(record.name, record.name.split(".")[-1].upper())
        level = record.levelname  # DEBUG / INFO / WARNING / ERROR / CRITICAL
        try:
            msg = self.format(record)
        except Exception:
            msg = record.getMessage()
        log_store.add(level, source, msg)


def setup_log_capture() -> None:
    handler = _LogStoreHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    for name in ("uvicorn.access", "uvicorn.error", "uvicorn", "fastapi"):
        lg = logging.getLogger(name)
        lg.addHandler(handler)
    # 앱 전용 로거
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.DEBUG)
    app_logger.addHandler(handler)
