# GitHub App + OAuth Worker setup (one-time, admin)

The review SPA signs users in via a GitHub App; a Cloudflare Worker
(`workers/oauth-exchange/`) swaps the OAuth `code` for a user token.
Until these steps are done, `APP_GH_CLIENT_ID` in `site/index.html` stays
empty and the sign-in UI is hidden.

## 1. Create the GitHub App (org sy-tools, manual — GitHub has no CLI for this)

Org **sy-tools** → Settings → Developer settings → GitHub Apps → New GitHub App:

- **Name**: `sy-subtitles-review`
- **Homepage URL**: `https://sy-tools.github.io/sy-subtitles/`
- **Callback URLs** (add both):
  - `https://sy-tools.github.io/sy-subtitles/`
  - `http://localhost:8000/`
- **Expire user authorization tokens**: OFF (the SPA has no refresh logic)
- **Request user authorization (OAuth) during installation**: ON
- **Webhook**: Inactive (uncheck Active)
- **Repository permissions**: Issues RW, Contents RW, Pull requests RW, Actions RW
  `Actions` is what lets the preview view render a video with burned-in
  subtitles: dispatching `burn-subtitles.yml`, polling run progress, and
  downloading the resulting artifact all go through the Actions API. Without it
  the button returns 403. After changing permissions, accept the organization's
  permission-update request; users may need to sign in again for their token to
  carry the new scope.
- **Where can this app be installed**: Only on this account

After creation: note the **Client ID** (`Iv1.…`), generate a **client secret**.

## 2. Install the App

App settings → Install App → sy-tools → Only select repositories →
`sy-subtitles`.

## 3. Set repo secrets (once)

The Worker is deployed by CI (`.github/workflows/deploy-worker.yml`), never
from a laptop. It needs four repo secrets:

```bash
gh secret set GH_OAUTH_CLIENT_ID      # the Iv1.… client id (step 1)
gh secret set GH_OAUTH_CLIENT_SECRET  # the generated client secret (step 1)
gh secret set CLOUDFLARE_ACCOUNT_ID   # see 3a
gh secret set CLOUDFLARE_API_TOKEN    # see 3b
```

### 3a. CLOUDFLARE_ACCOUNT_ID

A Cloudflare account on the **free plan** is enough (Workers free tier:
100k requests/day). After signing up at <https://dash.cloudflare.com>:

- Open **Workers & Pages** in the left menu. On the first visit Cloudflare
  asks you to register a `*.workers.dev` subdomain — pick one (e.g.
  `sy-tools`); the Worker URL becomes
  `https://sy-subtitles-oauth.<subdomain>.workers.dev`.
- The **Account ID** is shown in the right-hand column of the Workers & Pages
  overview page (also: it is the 32-hex-char segment in the dashboard URL,
  `dash.cloudflare.com/<account-id>/...`).

### 3b. CLOUDFLARE_API_TOKEN

1. Dashboard → profile icon (top-right) → **My Profile** → **API Tokens**
   (direct link: <https://dash.cloudflare.com/profile/api-tokens>).
2. **Create Token** → in the templates list pick **Edit Cloudflare Workers**
   → *Use template*.
3. On the token form:
   - **Account Resources**: *Include* → your account (the one from 3a).
   - **Zone Resources**: *All zones from an account* → your account. (The
     template bundles zone-level Workers-routes permissions; this deploy uses
     only workers.dev, so no zone is ever touched — but the template requires
     a selection.)
   - Optionally set **TTL** — but note an expired token silently breaks the
     deploy workflow later; no expiry + rotation on demand is simpler here.
4. **Continue to summary** → **Create Token**.
5. Copy the token — **it is shown exactly once**. Verify it works:

   ```bash
   curl -s https://api.cloudflare.com/client/v4/user/tokens/verify \
     -H "Authorization: Bearer <token>"   # expect "status": "active"
   ```

6. `gh secret set CLOUDFLARE_API_TOKEN` (paste the token).

This token can deploy/edit Workers on the account — treat it like a password:
it lives only in the repo secret, and can be revoked/rolled any time from the
same API Tokens page (then update the secret and re-run the workflow).

## 4. Deploy the Worker (CI)

The workflow deploys automatically on every merge to `main` that touches
`workers/oauth-exchange/**`, and can be run by hand:

```bash
gh workflow run deploy-worker.yml
```

It runs `wrangler deploy` and pushes `GH_CLIENT_ID`/`GH_CLIENT_SECRET` to the
Worker from the repo secrets. The deployed URL is
`https://sy-subtitles-oauth.<account-subdomain>.workers.dev` (shown in the run
log). Allowed origins live in `wrangler.toml` `[vars] ALLOWED_ORIGINS`.

## 5. Point the SPA at them

In `site/index.html` set:

```js
var APP_GH_CLIENT_ID = 'Iv1.…';
var APP_GH_EXCHANGE_URL = 'https://sy-subtitles-oauth.<account>.workers.dev/exchange';
```

Commit + deploy (Pages). The "Sign in" button appears for everyone; only
collaborators gain useful write actions.

## Local verification (before merging any of this)

Run the Worker locally instead of deploying:

```bash
cd workers/oauth-exchange
cp .dev.vars.example .dev.vars       # fill in the real Iv1.… id + secret
npx wrangler dev                      # serves http://localhost:8787
```

Then serve the SPA with the runtime hooks already injected:

```bash
python -m tools.serve_auth_local                  # SPA on :8000
open 'http://localhost:8000/?repo=sy-tools/sy-subtitles'
```

Click "Sign in" → GitHub → redirected back to localhost:8000 → the exchange
hits the local Worker. `http://localhost:8000` is already in the Worker's
`ALLOWED_ORIGINS` and must be one of the App's callback URLs (step 1) — the
port is not free to choose, and on any other one the round trip cannot
complete.

A bare `python -m http.server` does NOT work for this: it serves the files but
injects no hooks, and setting them from the console is too late — the OAuth
callback handler in `index.html` runs during page load, so the callback is
already consumed by the time you can type. That is the whole reason
`serve_auth_local` exists.

In a **worktree** there is no `.dev.vars` (it holds the App secret and is
gitignored). Run the Worker from the primary checkout instead of copying the
secret across; the SPA can still be served from the worktree, since the two are
separate processes on separate ports.

## Rotation / revocation

- Rotate the client secret: regenerate in the App settings, update the
  `GH_OAUTH_CLIENT_SECRET` repo secret, re-run `deploy-worker.yml`. Users stay
  signed in (tokens are unaffected).
- Revoke all user tokens: App settings → Advanced → Revoke all user tokens.
- A revoked/expired token in a browser triggers a silent sign-out on the next
  API call.
