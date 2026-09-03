const config = () => ({
  url: process.env.SUPABASE_URL,
  key: process.env.SUPABASE_PUBLISHABLE_KEY || process.env.SUPABASE_ANON_KEY,
});

export async function authenticatedRequest(req, path, options = {}) {
  const { url, key } = config();
  const token = (req.headers.authorization || "").replace(/^Bearer\s+/i, "");
  if (!url || !key || !token) return { error: "Unauthorized", status: 401 };

  const auth = await fetch(`${url}/auth/v1/user`, {
    headers: { apikey: key, Authorization: `Bearer ${token}` },
  });
  if (!auth.ok) return { error: "Unauthorized", status: 401 };

  const response = await fetch(`${url}/rest/v1/${path}`, {
    ...options,
    headers: {
      apikey: key,
      Authorization: `Bearer ${token}`,
      ...(options.headers || {}),
    },
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) return { error: body?.message || "Supabase request failed", status: response.status };
  return { body, response };
}

export function supabaseConfig() {
  return config();
}
