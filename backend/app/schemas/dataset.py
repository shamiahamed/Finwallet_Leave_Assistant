from typing import Any

from pydantic import BaseModel, Field


class DatasetSummary(BaseModel):
    dataset_id: str = Field(description="Stable identifier used in the X-Dataset-Id header.")
    name: str
    source: str = Field(description="'default' for the configured workbook, 'upload' otherwise.")
    schema_kind: str = Field(description="'known' when the known leave schema was detected.")
    row_counts: dict[str, int]
    size_bytes: int | None = None
    created_at: str
    validation_status: str = Field(description="'valid' or 'invalid'.")
    warnings: list[str] = Field(default_factory=list)


class DatasetPreview(BaseModel):
    dataset_id: str
    columns: list[str]
    sample_rows: list[dict[str, Any]]
    row_count: int
    column_count: int
    validation_status: str
    warnings: list[str] = Field(default_factory=list)


class DatasetListResponse(BaseModel):
    datasets: list[DatasetSummary]
    default_dataset_id: str


class UploadResponse(BaseModel):
    dataset: DatasetSummary
    preview: DatasetPreview
