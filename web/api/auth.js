import crypto from "node:crypto";

const COOKIE = "community_dashboard_session";
const MAX_AGE = 60 * 60 * 24 * 7;

function secret() {
  return process.env.DASHBOARD_AUTH_SECRET || "";
}

function sign(value) {
  return crypto.createHmac("sha256", secret()).update(value).digest("base64url");
}

function sameSecret(left, right) {
  const a = crypto.createHash("sha256").update(String(left)).digest();
  const b = crypto.createHash("sha256").update(String(right)).digest();
  return crypto.timingSafeEqual(a, b);
}

function sessionToken(email) {
  const payload = Buffer.from(
    JSON.stringify({ email, exp: Math.floor(Date.now() / 1000) + MAX_AGE }),
  ).toString("base64url");
  return `${payload}.${sign(payload)}`;
}

function validSession(req) {
  if (!secret()) return false;
  const raw = req.headers.cookie || "";
  const match = raw.match(new RegExp(`${COOKIE}=([^;]+)`));
  if (!match) return false;
  const [payload, signature] = match[1].split(".");
  if (!payload || !signature || !sameSecret(signature, sign(payload))) return false;
  try {
    const data = JSON.parse(Buffer.from(payload, "base64url").toString());
    return data.exp > Math.floor(Date.now() / 1000) && data.email === process.env.DASHBOARD_EMAIL;
  } catch {
    return false;
  }
}

export default async function handler(req, res) {
  if (req.method === "GET") {
    return res.status(200).json({ authenticated: validSession(req) });
  }
  if (req.method === "DELETE") {
    res.setHeader("Set-Cookie", `${COOKIE}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict`);
    return res.status(200).json({ authenticated: false });
  }
  if (req.method !== "POST") return res.status(405).json({ error: "Method not allowed" });

  const { email, password } = typeof req.body === "string" ? JSON.parse(req.body) : req.body || {};
  if (
    !secret() ||
    email !== process.env.DASHBOARD_EMAIL ||
    !sameSecret(password || "", process.env.DASHBOARD_PASSWORD || "")
  ) {
    return res.status(401).json({ error: "Invalid email or password" });
  }
  res.setHeader(
    "Set-Cookie",
    `${COOKIE}=${sessionToken(email)}; Path=/; Max-Age=${MAX_AGE}; HttpOnly; Secure; SameSite=Strict`,
  );
  return res.status(200).json({ authenticated: true });
}
