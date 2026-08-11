from enum import Enum

from pydantic import BaseModel, Field


class AccessStatus(str, Enum):
    JOIN = "join"
    APPLY = "apply"
    WATCH = "watch"
    REJECT = "reject"


class ValueTier(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    JUNK = "junk"


class SyncStatus(str, Enum):
    PENDING = "pending"
    SYNCED = "synced"
    ERROR = "error"
    SKIPPED = "skipped"


class Platform(str, Enum):
    CUSTOM = "custom"
    DISCORD = "discord"
    SKOOL = "skool"
    CIRCLE = "circle"
    SLACK = "slack"
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    MIGHTY = "mighty"
    FACEBOOK = "facebook"
    LINKEDIN = "linkedin"
    UNKNOWN = "unknown"


class NormalizedUrl(BaseModel):
    original_url: str
    website: str
    canonical_domain: str
    platform: Platform
    platform_id: str | None = None
    canonical_key: str
    is_blocked: bool = False
    block_reason: str | None = None


class DiscoveryHit(BaseModel):
    url: str
    title: str | None = None
    snippet: str | None = None
    provider: str
    query: str | None = None


class ExtractedCommunity(BaseModel):
    website: str
    canonical_key: str
    canonical_domain: str
    platform: Platform
    platform_id: str | None = None
    name: str | None = None
    niche: str | None = None
    audience: str | None = None
    geo: str | None = None
    join_url: str | None = None
    price_text: str | None = None
    price_amount: float | None = None
    currency: str | None = None
    size_text: str | None = None
    size_members: int | None = None
    contacts: dict = Field(default_factory=dict)
    is_professional: bool | None = None
    access_status: AccessStatus = AccessStatus.WATCH
    value_score: int = 0
    value_tier: ValueTier = ValueTier.LOW
    relevance_score: float = 0.0
    source_queries: list[str] = Field(default_factory=list)
    raw_signals: dict = Field(default_factory=dict)
    content_hash: str | None = None
    extraction_confidence: float = 0.0
    needs_llm: bool = False


class LlmExtractResult(BaseModel):
    price: float | None = None
    currency: str | None = None
    members_count: int | None = None
    is_professional: bool | None = None
    join_type: str | None = None
    confidence: float = 0.0
