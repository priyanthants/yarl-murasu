import { base64url, fromBase64url } from "./auth.js";

const textEncoder = new TextEncoder();
const textDecoder = new TextDecoder();

function config(env) {
  const repo = env.GITHUB_REPOSITORY || "";
  if (!/^[\w.-]+\/[\w.-]+$/.test(repo) || !env.GITHUB_WRITE_TOKEN) {
    throw new Error("GitHub repository or write token is not configured");
  }
  return { repo, branch: env.GITHUB_BRANCH || "main" };
}

function contentUrl(env, path) {
  const { repo, branch } = config(env);
  return `https://api.github.com/repos/${repo}/contents/${path}?ref=${encodeURIComponent(branch)}`;
}

function headers(env) {
  return {
    "Authorization": `Bearer ${env.GITHUB_WRITE_TOKEN}`,
    "Accept": "application/vnd.github+json",
    "User-Agent": "yarl-murasu-review"
  };
}

export async function getFile(env, path, fallback = null) {
  const response = await fetch(contentUrl(env, path), { headers: headers(env), cache: "no-store" });
  if (response.status === 404 && fallback !== null) return { data: fallback, sha: null };
  if (!response.ok) throw new Error(`GitHub read failed (${response.status})`);
  const file = await response.json();
  if (!file.content || !file.sha) throw new Error("GitHub returned no file content");
  const bytes = fromBase64url(file.content.replace(/\s/g, "").replace(/\+/g, "-").replace(/\//g, "_"));
  return { data: JSON.parse(textDecoder.decode(bytes)), sha: file.sha };
}

export async function putFile(env, path, data, sha, message) {
  const { branch } = config(env);
  const bytes = textEncoder.encode(JSON.stringify(data, null, 2) + "\n");
  const encoded = base64url(bytes).replace(/-/g, "+").replace(/_/g, "/");
  const body = { message, content: encoded.padEnd(Math.ceil(encoded.length / 4) * 4, "="), branch };
  if (sha) body.sha = sha;
  const response = await fetch(contentUrl(env, path), {
    method: "PUT", headers: { ...headers(env), "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (response.status === 409) return false;
  if (!response.ok) throw new Error(`GitHub write failed (${response.status})`);
  return true;
}

export function storyView(item, review = {}) {
  return {
    id: item.id,
    source: item.source || "",
    sourceUrl: item.link || "",
    originalTitle: item.title || "",
    published: item.published || "",
    image: item.image || "",
    state: review.state || "pending",
    revision: review.revision || 0,
    updatedAt: review.updated_at || "",
    updatedBy: review.updated_by || "",
    title: review.edits?.title ?? item.ai_title ?? "",
    summary: review.edits?.summary ?? item.ai_summary ?? "",
    body: review.edits?.body ?? item.ai_body ?? [],
    category: review.edits?.category ?? item.category ?? "srilanka"
  };
}

export async function listStories(env) {
  const [store, decisions] = await Promise.all([
    getFile(env, "data/fetched.json", { items: [] }),
    getFile(env, "data/reviews.json", { items: {} })
  ]);
  const reviews = decisions.data.items || {};
  return (store.data.items || [])
    .filter((item) => Array.isArray(item.ai_body) && item.ai_body.length && item.ai_title)
    .map((item) => storyView(item, reviews[item.id]))
    .sort((a, b) => b.published.localeCompare(a.published));
}

export function validateEdit(input) {
  if (!input || typeof input !== "object" || Array.isArray(input)) throw new Error("Invalid review request");
  const state = input.state;
  if (!["pending", "approved", "rejected"].includes(state)) throw new Error("Invalid review decision");
  const edits = input.edits || {};
  if (typeof edits !== "object" || Array.isArray(edits)) throw new Error("Invalid story edits");
  const title = String(edits.title || "").trim();
  const summary = String(edits.summary || "").trim();
  const body = Array.isArray(edits.body) && edits.body.every((p) => typeof p === "string")
    ? edits.body.map((p) => p.trim()).filter(Boolean) : [];
  const category = String(edits.category || "");
  if (title.length < 10 || title.length > 300) throw new Error("Headline must be 10–300 characters");
  if (summary.length < 10 || summary.length > 1000) throw new Error("Summary must be 10–1000 characters");
  if (!body.length || body.join("\n").length < 30 || body.join("\n").length > 12000) {
    throw new Error("Story body must be 30–12,000 characters");
  }
  if (!["jaffna", "srilanka", "world", "sports"].includes(category)) throw new Error("Invalid section");
  return { state, edits: { title, summary, body, category } };
}

export async function saveReview(env, id, input, login) {
  if (!/^[a-f0-9]{12}$/.test(id)) return { status: 400, error: "Invalid story ID" };
  const clean = validateEdit(input);
  const store = await getFile(env, "data/fetched.json", { items: [] });
  const item = (store.data.items || []).find((entry) => entry.id === id);
  if (!item || !item.ai_body || !item.ai_title) return { status: 404, error: "Story is no longer ready for review" };
  for (let attempt = 0; attempt < 3; attempt++) {
    const file = await getFile(env, "data/reviews.json", { items: {} });
    const reviews = file.data.items || {};
    const current = reviews[id] || {};
    if (Number(input.revision || 0) !== Number(current.revision || 0)) {
      return { status: 409, error: "Another editor changed this story. Reload before saving." };
    }
    const next = {
      ...current, ...clean, revision: (current.revision || 0) + 1,
      updated_at: new Date().toISOString(), updated_by: login
    };
    const updated = { ...file.data, items: { ...reviews, [id]: next } };
    if (await putFile(env, "data/reviews.json", updated, file.sha,
      `Review story: ${clean.state} ${id} by ${login}`)) {
      return { status: 200, story: storyView(item, next) };
    }
  }
  return { status: 409, error: "The review queue changed. Please try again." };
}
