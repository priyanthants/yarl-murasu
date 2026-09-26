import { randomBytes } from "node:crypto";
import { spawnSync } from "node:child_process";
import { generateVapidKeys } from "@mmmike/web-push/vapid";

function wrangler(args, input) {
  const result = spawnSync("wrangler", args, {
    cwd: new URL("..", import.meta.url).pathname,
    encoding: "utf8", input,
    env: { ...process.env, WRANGLER_SEND_METRICS: "false" }
  });
  if (result.status !== 0) throw new Error(`Wrangler failed while setting ${args.at(-1)}`);
  return result.stdout;
}

const existing = JSON.parse(wrangler(["secret", "list", "--format", "json"]));
const protectedNames = new Set(["SESSION_SECRET", "VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY"]);
if (existing.some(({ name }) => protectedNames.has(name))) {
  throw new Error("Push keys already exist. Refusing to rotate them and disconnect subscribed phones.");
}

const { publicKey, privateKey } = await generateVapidKeys();
const values = {
  SESSION_SECRET: randomBytes(32).toString("hex"),
  VAPID_PUBLIC_KEY: publicKey,
  VAPID_PRIVATE_KEY: privateKey
};
for (const [name, value] of Object.entries(values)) {
  wrangler(["secret", "put", name], `${value}\n`);
  console.log(`${name} installed in Cloudflare.`);
}
