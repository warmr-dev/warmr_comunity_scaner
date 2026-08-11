from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from community_scanner.models import (
    AccessStatus,
    ExtractedCommunity,
    LlmExtractResult,
    NormalizedUrl,
    Platform,
)

JOIN_PATTERNS = re.compile(
    r"\b(join|sign up|become a member|get started|subscribe)\b", re.I
)
APPLY_PATTERNS = re.compile(
    r"\b(apply|application|request to join|waitlist|waiting list)\b", re.I
)
PRICE_PATTERNS = re.compile(
    r"(?:\$|usd\s*)(\d{1,4}(?:[.,]\d{2})?)(?:\s*/\s*(mo|month|yr|year))?",
    re.I,
)
MEMBERS_PATTERNS = re.compile(
    r"([\d,.]+)\s*(members|member|people|subscribers|users)",
    re.I,
)


def _text(soup: BeautifulSoup) -> str:
    return " ".join(soup.stripped_strings)


def heuristic_extract(html: str, normalized: NormalizedUrl, query: str | None = None) -> ExtractedCommunity:
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.string.strip() if soup.title and soup.title.string else None
    h1 = soup.find("h1")
    name = (h1.get_text(strip=True) if h1 else None) or title
    body = _text(soup)

    access = AccessStatus.WATCH
    body_lc = body.lower()
    # Exclude adult/18+ content early.
    if re.search(r"(18\+|adult|porn|nsfw|explicit|onlyfans|hentai|lewd)", body_lc, flags=re.I):
        access = AccessStatus.REJECT
    if APPLY_PATTERNS.search(body):
        access = AccessStatus.APPLY
    elif JOIN_PATTERNS.search(body):
        access = AccessStatus.JOIN

    price_amount = None
    price_text = None
    currency = None
    m = PRICE_PATTERNS.search(body)
    if m:
        price_text = m.group(0)
        try:
            price_amount = float(m.group(1).replace(",", ""))
            currency = "USD"
        except ValueError:
            price_amount = None

    size_members = None
    size_text = None
    sm = MEMBERS_PATTERNS.search(body)
    if sm:
        size_text = sm.group(0)
        try:
            size_members = int(sm.group(1).replace(",", "").split(".")[0])
        except ValueError:
            size_members = None

    # Prefer direct invite links for Slack/WhatsApp when present.
    join_url = None
    join_url_meta: dict[str, str | None] = {}
    for a in soup.find_all("a", href=True):
        href = str(a.get("href") or "")
        href_lc = href.lower()
        anchor_text = a.get_text(" ", strip=True) or None

        # Slack invite
        if "slack.com" in href_lc and (
            "/invite/" in href_lc or "invite" in href_lc or "join" in href_lc
        ):
            join_url = urljoin(f"https://{normalized.canonical_domain}", href)
            join_url_meta = {
                "rule": "slack_invite_href",
                "href": href,
                "anchor_text": anchor_text,
            }
            break

        # WhatsApp invite / contact
        if ("wa.me" in href_lc) or (
            "whatsapp.com" in href_lc
            and ("invite" in href_lc or "join" in href_lc or "/send" in href_lc)
        ):
            join_url = urljoin(f"https://{normalized.canonical_domain}", href)
            join_url_meta = {
                "rule": "whatsapp_invite_href",
                "href": href,
                "anchor_text": anchor_text,
            }
            break

    if join_url:
        # Keep only non-empty URLs; normalize accidental whitespace.
        join_url = str(join_url).strip() or None

    if not join_url:
        for a in soup.find_all("a", href=True):
            href = str(a.get("href") or "")
            href_lc = href.lower()
            label = a.get_text(" ", strip=True) or None
            if (
                ("slack.com" in href_lc) or ("wa.me" in href_lc) or ("whatsapp.com" in href_lc)
            ) and (JOIN_PATTERNS.search(label or "") or APPLY_PATTERNS.search(label or "")):
                join_url = urljoin(
                    f"https://{normalized.canonical_domain}", href
                )
                join_url_meta = {
                    "rule": "join_label_href",
                    "href": href,
                    "anchor_text": label,
                }
                break

    emails = re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", body, flags=re.I)

    # Heuristic confidence: shared platforms with id are clearer; weak price/size → LLM
    confidence = 0.4
    if normalized.platform != Platform.CUSTOM and normalized.platform_id:
        confidence += 0.2
    if name:
        confidence += 0.1
    if join_url:
        confidence += 0.1
    if price_amount is not None:
        confidence += 0.05
    if size_members is not None:
        confidence += 0.05

    needs_llm = confidence < 0.7 or price_amount is None or size_members is None

    payload = {
        "name": name,
        "access": access.value,
        "price": price_amount,
        "size": size_members,
        "website": normalized.website,
    }
    content_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()

    return ExtractedCommunity(
        website=normalized.website,
        canonical_key=normalized.canonical_key,
        canonical_domain=normalized.canonical_domain,
        platform=normalized.platform,
        platform_id=normalized.platform_id,
        name=name,
        join_url=join_url,
        price_text=price_text,
        price_amount=price_amount,
        currency=currency,
        size_text=size_text,
        size_members=size_members,
        contacts={"emails": sorted(set(e.lower() for e in emails))[:5]},
        access_status=access,
        source_queries=[query] if query else [],
        raw_signals={
            "heuristic_confidence": confidence,
            **({"join_url_source": join_url_meta} if join_url_meta else {}),
        },
        content_hash=content_hash,
        extraction_confidence=min(confidence, 1.0),
        needs_llm=needs_llm,
    )


def merge_llm_result(item: ExtractedCommunity, llm: LlmExtractResult) -> ExtractedCommunity:
    data = item.model_dump()
    if llm.price is not None:
        data["price_amount"] = llm.price
    if llm.currency:
        data["currency"] = llm.currency
    if llm.members_count is not None:
        data["size_members"] = llm.members_count
    if llm.is_professional is not None:
        data["is_professional"] = llm.is_professional
    if llm.join_type == "join":
        data["access_status"] = AccessStatus.JOIN
    elif llm.join_type == "apply":
        data["access_status"] = AccessStatus.APPLY
    data["extraction_confidence"] = max(item.extraction_confidence, llm.confidence)
    data["needs_llm"] = False
    data["raw_signals"] = {
        **item.raw_signals,
        "llm": llm.model_dump(),
    }
    return ExtractedCommunity.model_validate(data)


def llm_extract_from_text(text: str, *, api_key: str, model: str) -> LlmExtractResult | None:
    """Light LLM pass for Watch/medium / low-confidence fields."""
    if not api_key:
        return None

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    prompt = (
        "Extract community metadata as JSON with keys: "
        "price (number|null), currency (string|null), members_count (int|null), "
        "is_professional (bool|null), join_type (join|apply|unknown), confidence (0..1). "
        "Ignore years, stock tickers, and unrelated dollar amounts.\n\n"
        f"TEXT:\n{text[:12000]}"
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    content = resp.choices[0].message.content or "{}"
    data: dict[str, Any] = json.loads(content)
    return LlmExtractResult.model_validate(data)
