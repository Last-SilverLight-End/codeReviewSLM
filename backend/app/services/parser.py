from dataclasses import dataclass

import tree_sitter_java as tsjava
import tree_sitter_javascript as tsjs
import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

# 언어별 파서 초기화
_PARSERS: dict[str, Parser] = {}

def _get_parser(language: str) -> Parser | None:
    if language in _PARSERS:
        return _PARSERS[language]

    lang_map = {
        "python": (tspython.language(), "python"),
        "javascript": (tsjs.language(), "javascript"),
        "java": (tsjava.language(), "java"),
    }
    if language not in lang_map:
        return None

    ptr, name = lang_map[language]
    lang = Language(ptr, name)
    parser = Parser()
    parser.set_language(lang)
    _PARSERS[language] = parser
    return parser


# 언어별 청킹 대상 노드 타입
_CHUNK_TYPES: dict[str, set[str]] = {
    "python": {"function_definition", "async_function_definition", "class_definition"},
    "javascript": {"function_declaration", "function_expression", "arrow_function", "class_declaration", "method_definition"},
    "java": {"method_declaration", "class_declaration", "constructor_declaration"},
}

# 파일 확장자 → 언어 매핑
EXTENSION_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "javascript",
    ".tsx": "javascript",
    ".java": "java",
    ".html": "html",
}

SUPPORTED_EXTENSIONS_TEXT = " ".join(EXTENSION_MAP.keys())


@dataclass
class CodeChunkData:
    chunk_type: str
    name: str | None
    content: str
    start_line: int
    end_line: int


def detect_language(filename: str) -> str | None:
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return EXTENSION_MAP.get(suffix)


def parse_code(code: str, language: str) -> list[CodeChunkData]:
    """코드를 함수/클래스 단위로 파싱해 청크 리스트 반환."""
    parser = _get_parser(language)
    if parser is None:
        # 지원하지 않는 언어는 파일 전체를 단일 청크로
        return [CodeChunkData(
            chunk_type="module",
            name=None,
            content=code,
            start_line=1,
            end_line=code.count("\n") + 1,
        )]

    tree = parser.parse(bytes(code, "utf-8"))
    target_types = _CHUNK_TYPES.get(language, set())
    chunks: list[CodeChunkData] = []

    _traverse(tree.root_node, code, target_types, chunks, depth=0)

    # 청크가 없으면 파일 전체를 module 청크로
    if not chunks:
        chunks.append(CodeChunkData(
            chunk_type="module",
            name=None,
            content=code,
            start_line=1,
            end_line=code.count("\n") + 1,
        ))

    return chunks


def _traverse(node: Node, code: str, target_types: set[str], chunks: list, depth: int) -> None:
    if node.type in target_types:
        name_node = node.child_by_field_name("name")
        name = name_node.text.decode("utf-8") if name_node else None

        chunks.append(CodeChunkData(
            chunk_type=_normalize_type(node.type),
            name=name,
            content=code[node.start_byte:node.end_byte],
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
        ))
        # 클래스 내부 메서드도 추출 (depth 1까지만)
        if depth < 1:
            for child in node.children:
                _traverse(child, code, target_types, chunks, depth + 1)
    else:
        for child in node.children:
            _traverse(child, code, target_types, chunks, depth)


def _normalize_type(node_type: str) -> str:
    if "class" in node_type:
        return "class"
    if "function" in node_type or "method" in node_type or "arrow" in node_type or "constructor" in node_type:
        return "function"
    return "module"
