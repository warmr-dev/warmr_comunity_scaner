from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parent
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/scanner.db")
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")
ENGINE = create_engine(DATABASE_URL, pool_pre_ping=True)


def json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


class DashboardHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload, status=200):
        body = json.dumps(payload, default=json_value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path):
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self._send_file(ROOT / "index.html")
        if parsed.path == "/api/stats":
            return self._stats()
        if parsed.path == "/api/communities":
            return self._communities(parse_qs(parsed.query))
        self._send_json({"error": "Not found"}, 404)

    def _stats(self):
        with ENGINE.begin() as conn:
            total = conn.execute(text("SELECT COUNT(*) FROM community_scanner")).scalar_one()
            platforms = conn.execute(
                text(
                    "SELECT platform, COUNT(*) AS count "
                    "FROM community_scanner GROUP BY platform ORDER BY count DESC"
                )
            ).mappings().all()
            tiers = conn.execute(
                text(
                    "SELECT value_tier, COUNT(*) AS count "
                    "FROM community_scanner GROUP BY value_tier ORDER BY count DESC"
                )
            ).mappings().all()
            free = conn.execute(
                text(
                    "SELECT COUNT(*) FROM community_scanner "
                    "WHERE price_amount IS NULL AND (price_text IS NULL OR price_text = '')"
                )
            ).scalar_one()
        return self._send_json(
            {
                "total": total,
                "free_or_unknown": free,
                "platforms": [dict(row) for row in platforms],
                "tiers": [dict(row) for row in tiers],
            }
        )

    def _communities(self, query):
        def first(name, default=""):
            return (query.get(name) or [default])[0].strip()

        try:
            limit = min(max(int(first("limit", "50")), 1), 100)
            offset = max(int(first("offset", "0")), 0)
        except ValueError:
            return self._send_json({"error": "Invalid pagination"}, 400)

        clauses = []
        params = {"limit": limit, "offset": offset}
        for field in ("platform", "value_tier", "access_status"):
            value = first(field)
            if value:
                clauses.append(f"{field} = :{field}")
                params[field] = value
        search = first("search")
        if search:
            clauses.append("(name ILIKE :search OR niche ILIKE :search OR website ILIKE :search)")
            params["search"] = f"%{search}%"
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        # PostgreSQL uses ILIKE; SQLite needs LIKE for the same case-insensitive search.
        if DATABASE_URL.startswith("sqlite") and search:
            where = where.replace("ILIKE", "LIKE")

        with ENGINE.begin() as conn:
            total = conn.execute(
                text(f"SELECT COUNT(*) FROM community_scanner {where}"), params
            ).scalar_one()
            rows = conn.execute(
                text(
                    "SELECT id, name, platform, niche, geo, website, join_url, "
                    "price_text, price_amount, currency, size_members, access_status, "
                    "value_score, value_tier, last_seen_at "
                    f"FROM community_scanner {where} "
                    "ORDER BY value_score DESC, last_seen_at DESC "
                    "LIMIT :limit OFFSET :offset"
                ),
                params,
            ).mappings().all()
        return self._send_json({"total": total, "items": [dict(row) for row in rows]})


if __name__ == "__main__":
    print(f"Dashboard listening on http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), DashboardHandler).serve_forever()
