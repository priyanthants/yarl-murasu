const encoder = new TextEncoder();
const decoder = new TextDecoder();

export function base64url(bytes) {
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function fromBase64url(value) {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
}

export function encodeText(value) { return base64url(encoder.encode(value)); }
export function decodeText(value) { return decoder.decode(fromBase64url(value)); }

export function cookie(request, name) {
  const pairs = (request.headers.get("Cookie") || "").split(";");
  const entry = pairs.find((part) => part.trim().startsWith(`${name}=`));
  return entry ? entry.trim().slice(name.length + 1) : "";
}

export function admins(env) {
  return new Set((env.ADMIN_LOGINS || "").split(",").map((s) => s.trim().toLowerCase()).filter(Boolean));
}

export function randomToken() {
  return base64url(crypto.getRandomValues(new Uint8Array(32)));
}

async function signingKey(secret) {
  return crypto.subtle.importKey("raw", encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}

export async function makeSession(login, secret) {
  const payload = encodeText(JSON.stringify({ login, exp: Date.now() + 30 * 86400000 }));
  const sig = await crypto.subtle.sign("HMAC", await signingKey(secret), encoder.encode(payload));
  return `${payload}.${base64url(new Uint8Array(sig))}`;
}

export async function sessionLogin(request, env) {
  if (!env.SESSION_SECRET) return null;
  const parts = cookie(request, "review_session").split(".");
  if (parts.length !== 2) return null;
  try {
    const valid = await crypto.subtle.verify("HMAC", await signingKey(env.SESSION_SECRET),
      fromBase64url(parts[1]), encoder.encode(parts[0]));
    if (!valid) return null;
    const payload = JSON.parse(decodeText(parts[0]));
    const login = String(payload.login || "").toLowerCase();
    return payload.exp > Date.now() && admins(env).has(login) ? login : null;
  } catch { return null; }
}

export function secureCookie(name, value, maxAge) {
  return `${name}=${value}; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=${maxAge}`;
}

export function sameOrigin(request) {
  return request.headers.get("Origin") === new URL(request.url).origin;
}

export function equalSecret(given, expected) {
  if (!given || !expected || given.length !== expected.length) return false;
  let mismatch = 0;
  for (let i = 0; i < given.length; i++) mismatch |= given.charCodeAt(i) ^ expected.charCodeAt(i);
  return mismatch === 0;
}
