import { randomBytes } from "node:crypto";
import { spawnSync } from "node:child_process";

const repo = "priyanthants/yarl-murasu";
const reviewUrl = "https://yarl-murasu-review.yarl-murasu-review.workers.dev";
const workdir = new URL("..", import.meta.url).pathname;

function command(binary, args, input, extraEnv = {}) {
  const result = spawnSync(binary, args, {
    cwd: workdir, encoding: "utf8", input,
    env: { ...process.env, WRANGLER_SEND_METRICS: "false", ...extraEnv }
  });
  if (result.status !== 0) throw new Error(`${binary} ${args.slice(0, 2).join(" ")} failed`);
  return result.stdout;
}

const credential = command("git", ["credential", "fill"], "protocol=https\nhost=github.com\n\n");
const token = credential.match(/^password=(.*)$/m)?.[1];
if (!token) throw new Error("An existing GitHub credential is needed to set the repository secret");
const githubEnv = { GH_TOKEN: token };
const user = command("gh", ["api", "user", "--jq", ".login"], undefined, githubEnv).trim();
if (user !== "priyanthants") throw new Error("The GitHub credential belongs to a different account");

const workerSecrets = JSON.parse(command("wrangler", ["secret", "list", "--format", "json"]));
if (workerSecrets.some(({ name }) => name === "REVIEW_INGEST_KEY")) {
  throw new Error("Alert key already exists in Cloudflare; refusing to rotate it unexpectedly");
}

const ingestKey = randomBytes(32).toString("hex");
command("gh", ["secret", "set", "REVIEW_INGEST_KEY", "--app", "actions", "--repo", repo],
  `${ingestKey}\n`, githubEnv);
command("gh", ["variable", "set", "REVIEW_API_URL", "--repo", repo, "--body", reviewUrl],
  undefined, githubEnv);
command("wrangler", ["secret", "put", "REVIEW_INGEST_KEY"], `${ingestKey}\n`);
console.log("Cloudflare and GitHub alert settings connected. The private key was not displayed or saved locally.");
