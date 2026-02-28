"""Auth models: UserRole enum, User, EngagementMember, MCPAPIKey, CopilotMessage."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.core.models.engagement import Engagement


class UserRole(enum.StrEnum):
    """User role levels for RBAC."""

    PLATFORM_ADMIN = "platform_admin"
    ENGAGEMENT_LEAD = "engagement_lead"
    PROCESS_ANALYST = "process_analyst"
    EVIDENCE_REVIEWER = "evidence_reviewer"
    CLIENT_VIEWER = "client_viewer"


class User(Base):
    """A platform user with role-based access control."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, values_callable=lambda e: [x.value for x in e]),
        default=UserRole.PROCESS_ANALYST,
        insert_default=UserRole.PROCESS_ANALYST,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, insert_default=True, nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # GDPR erasure fields (Issue #165)
    erasure_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    erasure_scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)

    # Relationships
    engagement_memberships: Mapped[list[EngagementMember]] = relationship(
        "EngagementMember", back_populates="user", cascade="all, delete-orphan"
    )
    consents: Mapped[list[UserConsent]] = relationship(
        "UserConsent", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', role={self.role})>"


class EngagementMember(Base):
    """Links users to engagements with a role-in-engagement override."""

    __tablename__ = "engagement_members"
    __table_args__ = (
        UniqueConstraint("engagement_id", "user_id", name="uq_engagement_user"),
        Index("ix_engagement_members_engagement_id", "engagement_id"),
        Index("ix_engagement_members_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_in_engagement: Mapped[str] = mapped_column(String(100), nullable=False, default="member")
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    engagement: Mapped[Engagement] = relationship("Engagement")
    user: Mapped[User] = relationship("User", back_populates="engagement_memberships")

    def __repr__(self) -> str:
        return f"<EngagementMember(engagement_id={self.engagement_id}, user_id={self.user_id})>"


class UserConsent(Base):
    """Tracks a user's consent grant or revocation for a specific consent type.

    Each row represents one consent event. The current state is the most
    recent row for a given (user_id, consent_type) pair (highest granted_at).
    Consent changes are immutable records for audit purposes.
    """

    __tablename__ = "user_consents"
    __table_args__ = (Index("ix_user_consents_user_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    consent_type: Mapped[str] = mapped_column(String(100), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True, default=None)

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="consents")

    def __repr__(self) -> str:
        return f"<UserConsent(user_id={self.user_id}, type='{self.consent_type}', granted={self.granted})>"


class MCPAPIKey(Base):
    """DB-persisted MCP API key for external tool access."""

    __tablename__ = "mcp_api_keys"
    __table_args__ = (
        UniqueConstraint("key_id", name="uq_mcp_api_keys_key_id"),
        Index("ix_mcp_api_keys_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    key_id: Mapped[str] = mapped_column(String(64), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship("User")

    def __repr__(self) -> str:
        return f"<MCPAPIKey(id={self.id}, key_id='{self.key_id}', client='{self.client_name}')>"


class CopilotMessage(Base):
    """Persisted copilot chat message for conversation history."""

    __tablename__ = "copilot_messages"
    __table_args__ = (
        Index("ix_copilot_messages_engagement_id", "engagement_id"),
        Index("ix_copilot_messages_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "user" or "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    query_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    citations: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    context_tokens_used: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<CopilotMessage(id={self.id}, role='{self.role}')>"
