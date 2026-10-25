from pydantic import BaseModel, ConfigDict


class ChatRequest(BaseModel):
    question: str
    conversation_id: str | None = None
    limit: int | None = None


class LLMMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: float


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    intent: str
    data: dict | list | None = None
    evidence: dict | None = None
    conversation_id: str | None = None
    metrics: LLMMetrics | None = None