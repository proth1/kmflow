"""Common response schemas shared across routes."""

from __future__ import annotations

from pydantic import BaseModel


class StatusResponse(BaseModel):
    status: str
    message: str | None = None


class DeleteResponse(BaseModel):
    deleted: bool
    id: str | None = None


class PaginatedMeta(BaseModel):
    total: int
    limit: int
    offset: int
