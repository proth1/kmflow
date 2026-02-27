"""Pydantic schemas for bitemporal validity and semantic relationship operations."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class BitempQueryFilter(BaseModel):
    """Filter for point-in-time queries on semantic relationships.

    When as_of_date is provided, only relationships where
    valid_from <= as_of_date AND (valid_to IS NULL OR valid_to > as_of_date)
    are returned. Retracted relationships are excluded unless include_retracted=True.
    """

    as_of_date: datetime | None = None
    include_retracted: bool = False


class SemanticRelationshipCreate(BaseModel):
    """Schema for creating a semantic relationship with bitemporal properties."""

    engagement_id: UUID
    source_node_id: str = Field(min_length=1, max_length=500)
    target_node_id: str = Field(min_length=1, max_length=500)
    edge_type: str = Field(min_length=1, max_length=100)
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class SupersedeRequest(BaseModel):
    """Schema for superseding one relationship with another."""

    old_relationship_id: UUID
    new_relationship_id: UUID


class SemanticRelationshipRead(BaseModel):
    """Schema for reading a semantic relationship."""

    id: str
    engagement_id: str
    source_node_id: str
    target_node_id: str
    edge_type: str
    asserted_at: str
    retracted_at: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    superseded_by: str | None = None
    created_at: str
