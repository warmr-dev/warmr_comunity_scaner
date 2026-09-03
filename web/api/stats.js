import { authenticatedRpc } from "./_supabase.js";

export default async function handler(req, res) {
  const result = await authenticatedRpc(req, "dashboard_stats");
  if (result.error) return res.status(result.status).json({ error: result.error });
  return res.status(200).json(result.body);
}
