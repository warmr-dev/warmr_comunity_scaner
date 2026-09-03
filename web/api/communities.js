import { authenticatedRequest } from "./_supabase.js";

function value(query, name, fallback = "") {
  return String(query?.[name] || fallback).trim();
}

export default async function handler(req, res) {
  if (req.method !== "GET") return res.status(405).json({ error: "Method not allowed" });
  const query = req.query || {};
  const limit = Math.min(Math.max(Number(value(query, "limit", "50")) || 50, 1), 100);
  const offset = Math.max(Number(value(query, "offset", "0")) || 0, 0);
  const filters = [];
  for (const field of ["platform", "value_tier", "access_status"]) {
    const item = value(query, field);
    if (item) filters.push(`${field}=eq.${encodeURIComponent(item)}`);
  }
  const search = value(query, "search");
  if (search) {
    const encoded = encodeURIComponent(`*${search}*`);
    filters.push(`or=(name.ilike.${encoded},niche.ilike.${encoded},website.ilike.${encoded})`);
  }

  const select = [
    "id", "name", "platform", "niche", "geo", "website", "join_url",
    "price_text", "price_amount", "currency", "size_members", "access_status",
    "value_score", "value_tier", "last_seen_at",
  ].join(",");
  const path = `community_scanner?select=${select}&order=value_score.desc,last_seen_at.desc&limit=${limit}&offset=${offset}${filters.length ? `&${filters.join("&")}` : ""}`;
  const result = await authenticatedRequest(req, path, {
    headers: { Prefer: "count=exact" },
  });
  if (result.error) return res.status(result.status).json({ error: result.error });

  const contentRange = result.response.headers.get("content-range") || "";
  const total = Number(contentRange.split("/")[1]) || (result.body || []).length;
  return res.status(200).json({ total, items: result.body || [] });
}
