# Phone review and notifications

This is a separate, installable editor app for Yarl Murasu. Automatically fetched and
rewritten news stays out of the public website until an editor approves it. The app
lets an editor read the source, edit the Tamil headline, summary, section and body,
then save as pending, approve, or reject. Approval commits `data/reviews.json` and
GitHub Actions rebuilds the public site. Rejection keeps the story out; an editor can
revisit either decision later. Locally authored posts still use the existing admin
panel and are not subject to this queue.

The phone app uses standard Web Push. It is designed for an iPhone Home Screen web
app now; the same app and per-device subscription store can support Android and
several admins later. No WhatsApp or Meta messaging account is needed.

## Before you begin

- A Cloudflare account with Workers and D1 enabled.
- Access to the `priyanthants/yarl-murasu` GitHub repository settings.
- Node.js 22 or newer. From this directory run `npm ci`.
- Do not paste or commit the OAuth secret, GitHub token, VAPID private key, or other
  generated secrets. Set them directly in Cloudflare and GitHub settings.

## Set up the Cloudflare app

1. Run `npx wrangler login` and finish Cloudflare authorization in your browser.
2. Run `npx wrangler d1 create review_db`. Replace
   `REPLACE_WITH_D1_DATABASE_ID` in `wrangler.jsonc` with the returned database ID.
3. Run `npm run db:remote` to create the subscription and notification tables.
4. Run `npm run deploy`. Note the `https://...workers.dev` address. The editor
   sign-in will show “not configured” until the next steps are finished.
5. In GitHub, create an **OAuth App** under Settings → Developer settings → OAuth
   Apps. Set its homepage to the Worker address and its callback URL to
   `https://YOUR-WORKER-ADDRESS/auth/callback`. Keep the client ID and secret.
6. In GitHub, create a **fine-grained personal access token** limited to this
   repository, with **Contents: Read and write**. This token is for the Worker to
   commit editorial decisions; do not use a `GITHUB_TOKEN` from Actions, because
   those commits would not trigger the publication workflow.
7. Run `npm run keys` once. Record the four values in a password manager. It prints
   two random app secrets and one Web Push key pair. Rotating the Web Push pair
   later means phones must enable notifications again.
8. Set these Worker secrets, entering each value at the prompt:

   ```sh
   npx wrangler secret put GITHUB_OAUTH_CLIENT_ID
   npx wrangler secret put GITHUB_OAUTH_CLIENT_SECRET
   npx wrangler secret put GITHUB_WRITE_TOKEN
   npx wrangler secret put SESSION_SECRET
   npx wrangler secret put REVIEW_INGEST_KEY
   npx wrangler secret put VAPID_PUBLIC_KEY
   npx wrangler secret put VAPID_PRIVATE_KEY
   ```

   `GITHUB_OAUTH_CLIENT_ID` is not confidential, but setting it alongside the
   other values keeps this setup simple. Keep `ADMIN_LOGINS` in `wrangler.jsonc`
   limited to trusted GitHub usernames. To add another admin later, separate
   usernames with commas and redeploy; each admin signs in and enables alerts on
   their own phone.

9. On GitHub, in the repository's Settings → Secrets and variables → Actions, add
   a **variable** `REVIEW_API_URL` with the Worker origin (no trailing slash), and
   a **secret** `REVIEW_INGEST_KEY` with exactly the same value used in Cloudflare.
   New draft alerts begin after the next news run. Until this is set, the
   approval gate still works and no push alerts are sent.

## Install on iPhone and check

1. Open the Worker URL in **Safari** on an iPhone running iOS 16.4 or newer.
2. Use Safari's Share menu → **Add to Home Screen**, then launch the new icon.
3. Sign in with the allowed GitHub account. Open the pending tab, edit a story,
   and save it as pending before making a publication decision.
4. Tap **Enable notifications** and allow the iPhone permission request. Tap
   **Send test** to check a notification reaches that phone.
5. Approve one draft. Watch the `Update news` GitHub Action complete, then check
   the live page. Reject a different draft and verify it stays off the site.

The app needs an internet connection. If notifications are denied, the queue still
works; enable notifications in iPhone Settings for the installed web app later.
Uninstalling the app or resetting website data invalidates its push subscription,
so enable notifications again after reinstalling.

## Safety and operational notes

- The authenticated app shows source links and drafts only to allowlisted admins.
  However, fetched source records and editorial decisions live in the **public
  GitHub repository**. They are not shown on the public website, but they should
  not be treated as confidential. A future private queue would need a storage
  migration.
- The public build checks the approval state on every run. An unapproved or
  rejected automatic story does not enter the homepage, article pages, feed,
  browser data, or share card.
- Draft alerts are limited to recent rewritten stories, at most five per news run.
  Cloudflare records notified story IDs to avoid repeat alerts. Every current
  allowlisted admin with an active subscription gets the same alert; editorial
  changes have a revision check and record who changed them.
- If Cloudflare, GitHub sign-in, or push delivery is unavailable, editors can
  still later review queued stories. The site does **not** auto-publish them.
- `npm run check` tests auth, edits, approval commits, and collision handling.
  `python3 ../scripts/selftest.py` checks that the public build respects approval.
