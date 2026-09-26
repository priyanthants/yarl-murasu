import { sendPushNotification } from "@mmmike/web-push/send";
import { admins, cookie, equalSecret, makeSession, randomToken, sameOrigin, secureCookie,
  sessionLogin } from "./auth.js";
import { listStories, saveReview } from "./github.js";

const json = (data, status = 200) => new Response(JSON.stringify(data), {
  status, headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff" }
});

function redirect(url, cookies = []) {
  const headers = new Headers({ Location: url, "Cache-Control": "no-store" });
  for (const value of cookies) headers.append("Set-Cookie", value);
  return new Response(null, { status: 302, headers });
}

async function oauthLogin(request, env) {
  if (!env.GITHUB_OAUTH_CLIENT_ID || !env.GITHUB_OAUTH_CLIENT_SECRET || !env.SESSION_SECRET) {
    return json({ error: "GitHub sign-in is not configured yet" }, 503);
  }
  const url = new URL(request.url);
  const state = randomToken();
  const target = new URL("https://github.com/login/oauth/authorize");
  target.searchParams.set("client_id", env.GITHUB_OAUTH_CLIENT_ID);
  target.searchParams.set("redirect_uri", `${url.origin}/auth/callback`);
  target.searchParams.set("scope", "read:user");
  target.searchParams.set("state", state);
  return redirect(target.toString(), [secureCookie("review_oauth_state", state, 600)]);
}

async function oauthCallback(request, env) {
  const url = new URL(request.url);
  const state = url.searchParams.get("state") || "";
  const code = url.searchParams.get("code") || "";
  if (!code || !equalSecret(state, cookie(request, "review_oauth_state"))) {
    return json({ error: "The sign-in request expired. Please try again." }, 400);
  }
  const tokenResponse = await fetch("https://github.com/login/oauth/access_token", {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ client_id: env.GITHUB_OAUTH_CLIENT_ID,
      client_secret: env.GITHUB_OAUTH_CLIENT_SECRET, code,
      redirect_uri: `${url.origin}/auth/callback`, state })
  });
  if (!tokenResponse.ok) return json({ error: "GitHub sign-in failed" }, 502);
  const token = (await tokenResponse.json()).access_token;
  if (!token) return json({ error: "GitHub did not authorize this sign-in" }, 403);
  const userResponse = await fetch("https://api.github.com/user", {
    headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json",
      "User-Agent": "yarl-murasu-review" }
  });
  if (!userResponse.ok) return json({ error: "Could not verify your GitHub account" }, 502);
  const login = String((await userResponse.json()).login || "").toLowerCase();
  if (!admins(env).has(login)) return json({ error: "This account is not an editor" }, 403);
  const session = await makeSession(login, env.SESSION_SECRET);
  return redirect(url.origin + "/", [
    secureCookie("review_oauth_state", "", 0),
    secureCookie("review_session", session, 30 * 86400)
  ]);
}

function validPushSubscription(subscription) {
  if (!subscription || typeof subscription.endpoint !== "string"
      || typeof subscription.keys?.p256dh !== "string"
      || typeof subscription.keys?.auth !== "string") return false;
  try {
    const url = new URL(subscription.endpoint);
    const host = url.hostname.toLowerCase();
    return url.protocol === "https:" && subscription.endpoint.length < 2048
      && (host.endsWith(".push.apple.com") || host === "fcm.googleapis.com"
          || host.endsWith(".push.services.mozilla.com"));
  } catch { return false; }
}

function vapid(env) {
  if (!env.VAPID_PUBLIC_KEY || !env.VAPID_PRIVATE_KEY) throw new Error("Web Push keys are not configured");
  return { publicKey: env.VAPID_PUBLIC_KEY, privateKey: env.VAPID_PRIVATE_KEY,
    subject: env.VAPID_SUBJECT || "https://priyanthants.github.io/yarl-murasu/" };
}

async function sendToRows(env, rows, payload) {
  const outcomes = await Promise.all(rows.map(async (row) => {
    try {
      const success = await sendPushNotification(JSON.parse(row.subscription_json), payload, vapid(env));
      if (success) return 1;
      await env.DB.prepare("DELETE FROM push_subscriptions WHERE endpoint = ?")
        .bind(row.endpoint).run();
    } catch (error) {
      // Never log subscription URLs: they act as device-specific bearer secrets.
      console.warn("Push delivery failed", error?.statusCode || error?.name || "unknown");
    }
    return 0;
  }));
  return outcomes.reduce((sum, value) => sum + value, 0);
}

async function notify(request, env) {
  if (!equalSecret(request.headers.get("X-Review-Ingest-Key") || "", env.REVIEW_INGEST_KEY || "")) {
    return json({ error: "Unauthorized" }, 401);
  }
  const stories = (await request.json()).stories;
  if (!Array.isArray(stories) || stories.length > 40) return json({ error: "Invalid batch" }, 400);
  const subscriptions = (await env.DB.prepare(
    "SELECT endpoint, login, subscription_json FROM push_subscriptions").all()).results || [];
  const rows = subscriptions.filter((row) => admins(env).has(row.login));
  if (!rows.length) return json({ notified: 0, devices: 0 });
  let notified = 0;
  for (const story of stories) {
    if (!/^[a-f0-9]{12}$/.test(story.id || "") || typeof story.title !== "string") continue;
    const seen = await env.DB.prepare("SELECT story_id FROM notified_stories WHERE story_id = ?")
      .bind(story.id).first();
    if (seen) continue;
    const delivered = await sendToRows(env, rows, {
      title: "புதிய செய்தி: உங்கள் ஒப்புதல் தேவை",
      body: story.title.slice(0, 180),
      url: `/?story=${encodeURIComponent(story.id)}`,
      tag: `story-${story.id}`
    });
    if (delivered) {
      await env.DB.prepare("INSERT OR IGNORE INTO notified_stories (story_id) VALUES (?)")
        .bind(story.id).run();
      notified++;
      if (notified >= 5) break;
    }
  }
  return json({ notified, devices: rows.length });
}

async function api(request, env, login) {
  const url = new URL(request.url);
  const path = url.pathname;
  if (request.method !== "GET" && !sameOrigin(request)) return json({ error: "Invalid origin" }, 403);
  if (path === "/api/me" && request.method === "GET") {
    return json({ login, vapidPublicKey: env.VAPID_PUBLIC_KEY || "" });
  }
  if (path === "/api/stories" && request.method === "GET") {
    return json({ stories: await listStories(env) });
  }
  const match = path.match(/^\/api\/stories\/([a-f0-9]{12})$/);
  if (match && request.method === "GET") {
    const story = (await listStories(env)).find((item) => item.id === match[1]);
    return story ? json({ story }) : json({ error: "Story not found" }, 404);
  }
  if (match && request.method === "PUT") {
    if (Number(request.headers.get("Content-Length") || 0) > 30000) return json({ error: "Draft too long" }, 413);
    try {
      const result = await saveReview(env, match[1], await request.json(), login);
      return json(result.status === 200 ? { story: result.story } : { error: result.error }, result.status);
    } catch (error) {
      if (/^(Invalid|Headline|Summary|Story body)/.test(error.message)) return json({ error: error.message }, 400);
      throw error;
    }
  }
  if (path === "/api/push/subscribe" && request.method === "POST") {
    const subscription = await request.json();
    if (!validPushSubscription(subscription)) return json({ error: "Invalid device subscription" }, 400);
    await env.DB.prepare(`INSERT INTO push_subscriptions (endpoint, login, subscription_json)
      VALUES (?, ?, ?) ON CONFLICT(endpoint) DO UPDATE SET login = excluded.login,
      subscription_json = excluded.subscription_json, updated_at = CURRENT_TIMESTAMP`)
      .bind(subscription.endpoint, login, JSON.stringify(subscription)).run();
    return json({ saved: true });
  }
  if (path === "/api/push/test" && request.method === "POST") {
    const rows = (await env.DB.prepare(
      "SELECT endpoint, subscription_json FROM push_subscriptions WHERE login = ?")
      .bind(login).all()).results || [];
    return json({ delivered: await sendToRows(env, rows, {
      title: "யாழ் முரசு அறிவிப்புகள் இயங்குகின்றன", body: "புதிய செய்திகளை இங்கே பெறுவீர்கள்.",
      url: "/", tag: "push-test" }) });
  }
  return json({ error: "Not found" }, 404);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    try {
      if (url.pathname === "/auth/login" && request.method === "GET") return oauthLogin(request, env);
      if (url.pathname === "/auth/callback" && request.method === "GET") return oauthCallback(request, env);
      if (url.pathname === "/auth/logout" && request.method === "GET") {
        return redirect(url.origin + "/", [secureCookie("review_session", "", 0)]);
      }
      if (url.pathname === "/internal/notify" && request.method === "POST") return notify(request, env);
      if (url.pathname.startsWith("/api/")) {
        const login = await sessionLogin(request, env);
        return login ? api(request, env, login) : json({ error: "Sign in required" }, 401);
      }
      if (request.method !== "GET") return json({ error: "Not found" }, 404);
      const asset = await env.ASSETS.fetch(request);
      const headers = new Headers(asset.headers);
      headers.set("Content-Security-Policy", "default-src 'self'; base-uri 'none'; form-action 'self'; "
        + "frame-ancestors 'none'; object-src 'none'");
      headers.set("Referrer-Policy", "no-referrer");
      headers.set("X-Content-Type-Options", "nosniff");
      return new Response(asset.body, { status: asset.status, statusText: asset.statusText, headers });
    } catch (error) {
      console.error("Review service error", error?.message || "unknown");
      return json({ error: "The review service could not complete this request" }, 500);
    }
  }
};
