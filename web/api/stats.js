import { authenticatedRequest } from "./_supabase.js";

export default async function handler(req, res) {
  const rows = [];
  for (let offset = 0; offset < 100000; offset += 1000) {
    const result = await authenticatedRequest(
      req,
      `community_scanner?select=platform,value_tier,price_amount,price_text&limit=1000&offset=${offset}`,
    );
    if (result.error) return res.status(result.status).json({ error: result.error });
    rows.push(...(result.body || []));
    if (!result.body || result.body.length < 1000) break;
  }
  const platforms = {};
  const tiers = {};
  let freeOrUnknown = 0;
  for (const row of rows) {
    platforms[row.platform] = (platforms[row.platform] || 0) + 1;
    tiers[row.value_tier] = (tiers[row.value_tier] || 0) + 1;
    if (row.price_amount == null && !row.price_text) freeOrUnknown += 1;
  }
  return res.status(200).json({
    total: rows.length,
    free_or_unknown: freeOrUnknown,
    platforms: Object.entries(platforms)
      .map(([platform, count]) => ({ platform, count }))
      .sort((a, b) => b.count - a.count),
    tiers: Object.entries(tiers).map(([value_tier, count]) => ({ value_tier, count })),
  });
}
