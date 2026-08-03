from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CommunityRow(Base):
    __tablename__ = "communities"
    __table_args__ = (UniqueConstraint("canonical_key", name="uq_communities_canonical_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    canonical_key: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    canonical_domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(64), nullable=False, default="custom")
    platform_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    website: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    niche: Mapped[str | None] = mapped_column(String(255), nullable=True)
    audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    geo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    join_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    size_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_members: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contacts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    access_status: Mapped[str] = mapped_column(String(32), nullable=False, default="watch")
    value_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    value_tier: Mapped[str] = mapped_column(String(32), nullable=False, default="low")
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_queries: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    raw_signals: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    last_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DiscoveryResultRow(Base):
    __tablename__ = "discovery_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    query: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_key: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PipelineRunRow(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
