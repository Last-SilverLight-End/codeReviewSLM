import io
import zipfile
from dataclasses import dataclass

from app.core.config import settings
from app.services.parser import CodeChunkData, detect_language, parse_code


@dataclass
class ParsedFile:
    filename: str        # zip 내부 상대 경로
    language: str
    content: str
    chunks: list[CodeChunkData]


def parse_zip(zip_bytes: bytes) -> list[ParsedFile]:
    """zip 바이트에서 지원 언어 파일만 추출해 파싱한 결과를 반환."""
    results: list[ParsedFile] = []

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        entries = [
            e for e in zf.infolist()
            if not e.is_dir()
            and not _is_hidden(e.filename)
            and e.file_size <= settings.MAX_FILE_SIZE_BYTES
        ]

        for entry in entries[:settings.MAX_FILES_PER_PROJECT]:
            # 파일명의 마지막 부분(basename)으로 언어 감지
            basename = entry.filename.split("/")[-1]
            language = detect_language(basename)
            if language is None:
                continue

            try:
                raw = zf.read(entry.filename)
                content = raw.decode("utf-8", errors="replace")
            except Exception:
                continue

            chunks = parse_code(content, language)
            results.append(ParsedFile(
                filename=entry.filename,
                language=language,
                content=content,
                chunks=chunks,
            ))

    return results


def _is_hidden(path: str) -> bool:
    """node_modules, .git, __pycache__ 등 무시할 경로 확인."""
    skip = set(settings.IGNORE_DIRS)
    parts = set(path.replace("\\", "/").split("/"))
    return bool(parts & skip)
