from datetime import datetime

from pydantic import BaseModel

from app.schemas.chat import ModelOptions


class ReviewRequest(BaseModel):
    file_id: int
    model_options: ModelOptions = ModelOptions()


class QuickReviewResponse(BaseModel):
    filename: str
    language: str
    result: str


class ReviewResponse(BaseModel):
    id: int
    file_id: int
    status: str
    result: str | None = None
    error: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
