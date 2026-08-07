from __future__ import annotations

import argparse
import json

from community_scanner.config import get_settings
from community_scanner.discovery import QueryParams
from community_scanner.models import Base
from community_scanner.pipeline import run_pipeline
from community_scanner.store import make_engine, make_session_factory
from community_scanner.sync import dry_run_sync, sync_rows_to_warmr


def cmd_init_db(_: argparse.Namespace) -> None:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    print("OK: tables created")


def cmd_discover(args: argparse.Namespace) -> None:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    Session = make_session_factory(settings.database_url)
    params = QueryParams(geo=args.geo, niche=args.niche, audience=args.audience)
    with Session() as session:
        result = run_pipeline(
            session,
            settings,
            params,
            query_limit=args.queries,
            per_query=args.per_query,
            max_fetch=args.max_fetch,
            use_llm=args.llm,
        )
    print(json.dumps({"run_id": result.run_id, "metrics": result.metrics.as_dict()}, indent=2))


def cmd_sync_dry(args: argparse.Namespace) -> None:
    settings = get_settings()
    Session = make_session_factory(settings.database_url)
    with Session() as session:
        payloads = dry_run_sync(session, settings.sync_value_tier_list)
    print(json.dumps({"count": len(payloads), "payloads": payloads[: args.limit]}, indent=2))


def cmd_sync_warmr(args: argparse.Namespace) -> None:
    settings = get_settings()
    if not settings.warmr_database_url:
        raise SystemExit("WARMR_DATABASE_URL is empty. Set it in .env to enable sync.")

    scanner_session_factory = make_session_factory(settings.database_url)
    warmr_engine = make_engine(settings.warmr_database_url)
    WarmrSession = lambda: None  # placeholder; we create session via sessionmaker below
    from sqlalchemy.orm import sessionmaker

    warmr_session_factory = sessionmaker(bind=warmr_engine, autoflush=False, autocommit=False)

    value_tiers = [t.strip() for t in args.value_tiers.split(",") if t.strip()]

    with scanner_session_factory() as scanner_session, warmr_session_factory() as warmr_session:
        count = sync_rows_to_warmr(
            scanner_session,
            warmr_session,
            value_tiers,
            warmr_table_name=args.table,
            upsert_key=args.upsert_key,
        )

    print(json.dumps({"synced": count, "table": args.table, "upsert_key": args.upsert_key}, indent=2))


def cmd_list(args: argparse.Namespace) -> None:
    from sqlalchemy import select

    from community_scanner.models import CommunityRow

    settings = get_settings()
    Session = make_session_factory(settings.database_url)
    with Session() as session:
        rows = list(session.scalars(select(CommunityRow).limit(args.limit)))
    payload = [
        {
            "canonical_key": r.canonical_key,
            "name": r.name,
            "website": r.website,
            "platform": r.platform,
            "access_status": r.access_status,
            "value_tier": r.value_tier,
            "value_score": r.value_score,
            "price_amount": r.price_amount,
            "size_members": r.size_members,
        }
        for r in rows
    ]
    print(json.dumps({"count": len(payload), "communities": payload}, indent=2, ensure_ascii=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="community-scanner")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-db", help="Create DB tables (SQLite or Postgres)")
    p_init.set_defaults(func=cmd_init_db)

    p_disc = sub.add_parser("run", help="Run discovery + extract + classify pipeline")
    p_disc.add_argument("--niche", default="accounting")
    p_disc.add_argument("--geo", default="Florida")
    p_disc.add_argument("--audience", default="CPAs")
    p_disc.add_argument("--queries", type=int, default=5)
    p_disc.add_argument("--per-query", type=int, default=10)
    p_disc.add_argument("--max-fetch", type=int, default=40)
    p_disc.add_argument("--llm", action="store_true", help="Force LLM extract pass")
    p_disc.set_defaults(func=cmd_discover)

    p_sync = sub.add_parser("sync-dry-run", help="Show payloads ready for Warmr DB")
    p_sync.add_argument("--limit", type=int, default=20)
    p_sync.set_defaults(func=cmd_sync_dry)

    p_sync_write = sub.add_parser("sync-warmr", help="Write communities into Warmr DB (upsert)")
    p_sync_write.add_argument("--value-tiers", default="high,medium")
    p_sync_write.add_argument("--table", default="communities")
    p_sync_write.add_argument("--upsert-key", default="canonical_key")
    p_sync_write.set_defaults(func=cmd_sync_warmr)

    p_list = sub.add_parser("list", help="List communities in local DB")
    p_list.add_argument("--limit", type=int, default=50)
    p_list.set_defaults(func=cmd_list)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
