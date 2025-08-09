from pydantic import BaseModel, Field
from typing import Optional, List, Literal


class Iteration(BaseModel):
    role: Literal["agent", "user", "website"]
    content: str
    timestamp: str
    edits: Optional[List[str]] = None
    image_path: Optional[str] = None


class Session(BaseModel):
    id: str
    status: Literal[
        "created",
        "processing",
        "waiting_for_frontend",
        "applied_edit",
        "completed",
        "error",
    ]
    max_iterations: int
    current_iteration: int = 0
    html: str
    current_html: str
    pending_html: Optional[str] = None
    original_query: str
    message: Optional[str] = None
    error: Optional[str] = None
    iterations: List[Iteration] = Field(default_factory=list)
    created_at: str
    updated_at: str
    completed_at: Optional[str] = None


class SharedConfiguration(BaseModel):
    id: str
    original_url: str
    modified_html: str
    title: str
    description: Optional[str] = None
    created_at: str
    expires_at: Optional[str] = None
    view_count: int = 0


class CreateShareRequest(BaseModel):
    url: str
    html: str
    title: str
    description: Optional[str] = None
    expires_in_days: Optional[int] = 30  # Default 30 days expiration


class CreateShareResponse(BaseModel):
    share_id: str
    shareable_url: str
    message: str


class GetShareResponse(BaseModel):
    original_url: str
    modified_html: str
    title: str
    description: Optional[str] = None
    created_at: str
