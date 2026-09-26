import { randomBytes } from "node:crypto";
import { generateVapidKeys } from "@mmmike/web-push/vapid";

const { publicKey, privateKey } = await generateVapidKeys();
console.log("Keep these values private. Add the first three as Cloudflare Worker secrets:");
console.log(`SESSION_SECRET=${randomBytes(32).toString("hex")}`);
console.log(`REVIEW_INGEST_KEY=${randomBytes(32).toString("hex")}`);
console.log(`VAPID_PRIVATE_KEY=${privateKey}`);
console.log("Add this one as the Worker VAPID_PUBLIC_KEY variable:");
console.log(`VAPID_PUBLIC_KEY=${publicKey}`);
