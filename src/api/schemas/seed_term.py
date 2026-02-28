"""Pydantic schemas for SeedTerm CRUD operations."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from src.core.models.seed_term import TermCategory, TermSource


class SeedTermCreate(BaseModel):
    """Schema for creating a seed term."""

    engagement_id: UUID
    term: str = Field(min_length=1, max_length=500)
    domain: str = Field(min_length=1, max_length=200)
    category: TermCategory
    source: TermSource


class SeedTermMergeRequest(BaseModel):
    """Schema for merging one seed term into another."""

    deprecated_term_id: UUID
    canonical_term_id: UUID


class SeedTermRead(BaseModel):
    """Schema for reading a seed term."""

    id: str
    engagement_id: str
    term: str
    domain: str
    category: str
    source: str
    status: str
    merged_into: str | None = None
    created_at: str
