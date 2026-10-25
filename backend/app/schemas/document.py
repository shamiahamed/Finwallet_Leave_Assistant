# Document (RAG) upload/list and retrieval-answer schemas.
from pydantic import BaseModel, Field


class DocumentSummary(BaseModel):
    document_id: str
    name: str
    source: str
    page_count: int
    chunk_count: int
    size_bytes: int | None = None
    created_at: str


class DocumentListResponse(BaseModel):
    documents: list[DocumentSummary]


class DocumentUploadResponse(BaseModel):
    document: DocumentSummary


class DocumentChunkOut(BaseModel):
    document_id: str
    document_name: str
    page: int | None = None
    score: float
    text: str


class DocumentAnswer(BaseModel):
    question: str
    answer: str = Field(description="Grounded answer, or a clear 'not enough evidence' notice.")
    matched: bool = Field(description="True when at least one relevant passage was found.")
    sources: list[DocumentChunkOut] = Field(default_factory=list)
