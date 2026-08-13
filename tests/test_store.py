from sqlalchemy.orm import Session

from community_scanner.models import AccessStatus, ExtractedCommunity, Platform, ValueTier
from community_scanner.models.db import Base, CommunityRow
from community_scanner.store import make_engine, upsert_community


def _sample_item(*, canonical_key: str, join_url: str) -> ExtractedCommunity:
    return ExtractedCommunity(
        website=join_url,
        canonical_key=canonical_key,
        canonical_domain="discord.gg",
        platform=Platform.DISCORD,
        platform_id=canonical_key.split(":", 1)[-1],
        name="Test community",
        geo="USA",
        join_url=join_url,
        access_status=AccessStatus.JOIN,
        value_score=30,
        value_tier=ValueTier.LOW,
        source_queries=["test"],
        raw_signals={"harvest": True},
    )


def test_upsert_community_dedupes_pending_rows_in_same_transaction():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        item_a = _sample_item(
            canonical_key="telegram:changenow_chat",
            join_url="https://t.me/changenow_chat",
        )
        item_b = _sample_item(
            canonical_key="telegram:changenow_chat",
            join_url="https://t.me/changenow_chat",
        )

        _, created_a, _ = upsert_community(session, item_a)
        _, created_b, _ = upsert_community(session, item_b)

        assert created_a is True
        assert created_b is False
        session.commit()

        rows = session.query(CommunityRow).all()
        assert len(rows) == 1
        assert rows[0].canonical_key == "telegram:changenow_chat"
