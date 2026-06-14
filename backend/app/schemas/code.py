from pydantic import BaseModel


class CodeChunkResponse(BaseModel):
    id: int
    chunk_type: str
    name: str | None
    content: str
    start_line: int
    end_line: int

    model_config = {"from_attributes": True}


class UploadResponse(BaseModel):
    file_id: int
    filename: str
    language: str
    chunk_count: int


class SearchResponse(BaseModel):
    chunks: list[CodeChunkResponse]


class ProjectUploadResponse(BaseModel):
    project_id: int
    name: str
    file_count: int
    chunk_count: int


class ProjectResponse(BaseModel):
    id: int
    name: str
    file_count: int
    chunk_count: int
    created_at: str
