import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { admins, makeSession, sessionLogin } from "../src/auth.js";
import { saveReview, validateEdit } from "../src/github.js";
import worker from "../src/worker.js";

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

const env = {
  ADMIN_LOGINS: "priyanthants, second-editor",
  SESSION_SECRET: "a-long-random-test-secret",
  GITHUB_REPOSITORY: "priyanthants/yarl-murasu",
  GITHUB_BRANCH: "main",
  GITHUB_WRITE_TOKEN: "test-token"
};
const item = {
  id: "012345abcdef", type: "auto", title: "Original story", ai_title: "தமிழில் புதிய செய்தியின் தலைப்பு",
  ai_summary: "தமிழில் செய்திக்கான முழுமையான சுருக்கம் இங்கே உள்ளது.",
  ai_body: ["தமிழில் வெளியீட்டுக்கான முழுமையான செய்தி உரை இங்கே இடம்பெற்றுள்ளது."],
  category: "jaffna", published: "2026-09-27T00:00:00Z"
};
const edits = { title: item.ai_title, summary: item.ai_summary, body: item.ai_body, category: "jaffna" };
const encoded = (value) => Buffer.from(JSON.stringify(value)).toString("base64");
const ghFile = (value, sha) => Response.json({ content: encoded(value), sha });

test("only configured admins can use signed sessions", async () => {
  assert.deepEqual([...admins(env)], ["priyanthants", "second-editor"]);
  const signed = await makeSession("priyanthants", env.SESSION_SECRET);
  const request = (token) => new Request("https://review.example/api/me", {
    headers: { Cookie: `review_session=${token}` }
  });
  assert.equal(await sessionLogin(request(signed), env), "priyanthants");
  assert.equal(await sessionLogin(request(`${signed}tampered`), env), null);
  assert.equal(await sessionLogin(request(await makeSession("not-admin", env.SESSION_SECRET)), env), null);
});

test("review edits must be publishable and decisions explicit", () => {
  assert.deepEqual(validateEdit({ state: "approved", edits }), { state: "approved", edits });
  assert.throws(() => validateEdit({ state: "approved", edits: { ...edits, body: [] } }), /Story body/);
  assert.throws(() => validateEdit({ state: "approved", edits: { ...edits, category: "unknown" } }), /Invalid section/);
  assert.throws(() => validateEdit({ state: "published", edits }), /Invalid review decision/);
  assert.throws(() => validateEdit(null), /Invalid review request/);
});

test("an approval commits edited content and records the editor", async () => {
  let committed;
  globalThis.fetch = async (url, options = {}) => {
    if (options.method === "PUT") {
      committed = JSON.parse(options.body);
      return Response.json({ content: { sha: "new-sha" } });
    }
    if (String(url).includes("fetched.json")) return ghFile({ items: [item] }, "store-sha");
    return ghFile({ items: {} }, "review-sha");
  };
  const result = await saveReview(env, item.id, { state: "approved", edits, revision: 0 }, "priyanthants");
  assert.equal(result.status, 200);
  assert.equal(result.story.state, "approved");
  assert.equal(result.story.revision, 1);
  assert.match(committed.message, /^Review story: approved 012345abcdef by priyanthants$/);
  const saved = JSON.parse(Buffer.from(committed.content, "base64").toString("utf8"));
  assert.equal(saved.items[item.id].updated_by, "priyanthants");
  assert.deepEqual(saved.items[item.id].edits, edits);
});

test("a stale editor cannot overwrite a newer decision", async () => {
  let wrote = false;
  globalThis.fetch = async (url, options = {}) => {
    if (options.method === "PUT") { wrote = true; return Response.json({}); }
    if (String(url).includes("fetched.json")) return ghFile({ items: [item] }, "store-sha");
    return ghFile({ items: { [item.id]: { state: "rejected", revision: 2 } } }, "review-sha");
  };
  const result = await saveReview(env, item.id, { state: "approved", edits, revision: 1 }, "second-editor");
  assert.equal(result.status, 409);
  assert.equal(wrote, false);
});

test("review APIs require a session and reject cross-origin writes", async () => {
  const anonymous = await worker.fetch(new Request("https://review.example/api/stories"), env);
  assert.equal(anonymous.status, 401);
  const signed = await makeSession("priyanthants", env.SESSION_SECRET);
  const request = new Request(`https://review.example/api/stories/${item.id}`, {
    method: "PUT", headers: { Cookie: `review_session=${signed}`, Origin: "https://another.example" },
    body: JSON.stringify({ state: "approved", edits, revision: 0 })
  });
  const response = await worker.fetch(request, env);
  assert.equal(response.status, 403);
});
