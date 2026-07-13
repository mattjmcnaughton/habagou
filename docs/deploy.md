# Deploy: Fly.io cutover and runbook

Production is a public Fly.io app (`habagou`) with Postgres on [Neon](https://neon.tech/)
(Neon project **`habagou`**, Free tier, pooled endpoint).
Continuous deployment: merge to `main` → CI green → semantic-release → (in
parallel) publish image to GHCR **and** `flyctl deploy --remote-only` (Fly
builds from the release tag) → Fly `release_command` runs migrate / import /
seed once. GHCR is an artifact mirror; Fly does not pull from it (private GHCR
is not pullable by Fly).

Local prod-like smoke still uses Docker Compose (`just compose-up` /
`just compose-smoke`); that path bootstraps on container start and is unrelated
to Fly cutover.

## Prerequisites

- Fly account + [flyctl](https://fly.io/docs/flyctl/install/) installed and
  authenticated (`flyctl auth login`).
- Neon project **`habagou`** with a **pooled** connection string. Do **not** paste Neon's
  default URL as-is. Neon copies look like
  `postgresql://…@….neon.tech/neondb?sslmode=require&channel_binding=require`
  — rewrite for this app (SQLAlchemy async + asyncpg):
  1. `postgresql://` → `postgresql+asyncpg://` (plain scheme loads psycopg2)
  2. `sslmode=require` → `ssl=require` (asyncpg rejects `sslmode`)
  3. Drop `channel_binding=…` (asyncpg rejects `channel_binding`)
  Final form: `postgresql+asyncpg://USER:PASSWORD@HOST/DB?ssl=require`
  (`DATABASE_URL` may already be set as a Fly secret before first deploy.)
- GitHub repo access to add the `FLY_API_TOKEN` Actions secret.
- An Auth0 tenant and a **Regular Web Application** for the production login
  flow. Register `https://<custom-domain>/auth/callback` as an **Allowed
  Callback URL**. Auth0 is the production OIDC provider; Keycloak remains the
  local and CI provider (see [auth.md](auth.md)).
- A custom domain you control. For Habagou this is typically
  `habagou.mattjmcnaughton.com`; DNS is managed in
  [mattjmcnaughton/nuage](https://github.com/mattjmcnaughton/nuage)
  (see the Habagou record addition in
  [ac6a774](https://github.com/mattjmcnaughton/nuage/commit/ac6a774c7f8d3d2ba218a1c338c906aa838757b8)).
  Certs need an allocated Fly IP, so create the app and do a first deploy
  before DNS.

## One-time cutover (order matters)

Do these steps in order. App + secrets must exist before the first deploy
because `release_command` must reach Neon on the first run. Custom domain /
certs come **after** the first deploy.

### 1. Create the Fly app

Use `apps create` (not `fly launch`) — `fly.toml` is already in the repo:

```sh
flyctl apps create habagou
```

Confirm `app = 'habagou'` in `fly.toml` matches.

### 2. Set secrets

```sh
# Required — Neon pooled URL rewritten for asyncpg + SSL.
# Neon console copies look like:
#   postgresql://neondb_owner:…@….neon.tech/neondb?sslmode=require&channel_binding=require
# Rewrite before setting (app also normalizes these in config.py):
#   1. postgresql://     →  postgresql+asyncpg://
#   2. Prefer the pooled hostname (often contains -pooler)
#   3. sslmode=require   →  ssl=require   (asyncpg rejects sslmode=)
#   4. Drop channel_binding=…            (asyncpg rejects channel_binding=)
flyctl secrets set DATABASE_URL='postgresql+asyncpg://neondb_owner:…@….neon.tech/neondb?ssl=require'

# Required — OIDC client credentials and session signing key.
# OIDC_PROVIDER=auth0 and SESSION_COOKIE_SECURE=true are committed non-secret
# Fly configuration. Replace the tenant and client values below.
python -c 'import secrets; print(secrets.token_urlsafe(32))'
flyctl secrets set \
  SESSION_SECRET_KEY='<random value above>' \
  OIDC_ISSUER='https://<tenant>.auth0.com/' \
  OIDC_CLIENT_ID='<Auth0 Regular Web Application client ID>' \
  OIDC_CLIENT_SECRET='<Auth0 Regular Web Application client secret>'
```

A plain `postgresql://…` secret makes Alembic/SQLAlchemy load **psycopg2**,
which is not installed (`ModuleNotFoundError: No module named 'psycopg2'`).
Neon's `sslmode=require` and `channel_binding=require` query params cause
`TypeError: connect() got an unexpected keyword argument '…'` with asyncpg —
use `?ssl=require` only. `src/habagou/config.py` rewrites/strips these on
load, but set the secret correctly so other tools see the same URL.

`fly secrets` replaces the old AWS Secrets Manager + External Secrets Operator
path. Non-secret config lives in `fly.toml` `[env]` (including
`HABAGOU_RUN_BOOTSTRAP=0` so app machines skip bootstrap, plus
`OIDC_PROVIDER=auth0` and `SESSION_COOKIE_SECURE=true`).

### Auth0 configuration

Create an Auth0 **Regular Web Application**. Its callback URL must be the
public, HTTPS application URL followed by `/auth/callback`:

```text
https://<custom-domain>/auth/callback
```

Set the tenant's issuer, client ID, and client secret as Fly secrets in the
previous step. The app uses discovery at
`$OIDC_ISSUER/.well-known/openid-configuration`; do not set
`OIDC_METADATA_URL` for a standard Auth0 tenant. The default requested scopes
are `openid profile email`.

The current `POST /auth/logout` clears only Habagou's local session. It does
not redirect to Auth0's logout endpoint, so an Auth0 Allowed Logout URL is not
required yet. Add `https://<custom-domain>/` before enabling provider logout in
the future.

On a brand-new app, secrets are often **Staged** until Machines exist
(`fly secrets list` will say so). `fly secrets deploy` cannot run yet
("no machines available"). The first-deploy steps below create Machines so
secrets become live.

### 3. First manual deploy

Watch the release machine so migrations/import/seed succeed before enabling CD.

If secrets are still **Staged** and a previous deploy failed during
`release_command` (common chicken-and-egg: no Machines yet, so secrets never
became live), bootstrap Machines first, then run a full deploy:

```sh
# From this checkout (or a release tag)
# 1) Create Machines without running migrate/import/seed
flyctl deploy --app habagou --remote-only --skip-release-command

# 2) Confirm secrets are no longer Staged
flyctl secrets list -a habagou
# If still Staged (Machines now exist):
flyctl secrets deploy -a habagou

# 3) Full deploy — release_command runs migrate/import/seed with DATABASE_URL
flyctl deploy --app habagou --remote-only
```

If secrets are already live (`fly secrets list` does not say Staged), a single
full deploy is enough:

```sh
flyctl deploy --app habagou --remote-only
```

What to expect:

- Fly runs `release_command` (`true`); the image `ENTRYPOINT`
  (`docker/entrypoint.sh`) still runs with `RELEASE_COMMAND=1`, so it migrates,
  imports the stroke corpus, and seeds.
- Neon Free may be cold — the entrypoint retries DB migrations
  (`HABAGOU_BOOTSTRAP_ATTEMPTS`, default 10).
- After release succeeds, app machines start with bootstrap skipped and serve
  on the Fly proxy (`https://habagou.fly.dev`).

Useful checks:

```sh
flyctl logs -a habagou
flyctl releases -a habagou
curl -fsS https://habagou.fly.dev/readyz
```

### 4. Custom domain + DNS + TLS

Do this only after a successful deploy so the app has allocated IPs.

#### 4a. Attach the hostname

```sh
flyctl certs add <custom-domain> -a habagou
# Optional www (or other subdomain):
flyctl certs add www.<custom-domain> -a habagou
```

`fly certs add` prints the DNS records Fly expects. Re-print them anytime with:

```sh
flyctl certs setup <custom-domain> -a habagou
flyctl ips list -a habagou   # A / AAAA targets if using address records
```

If IPv4/IPv6 are missing:

```sh
flyctl ips allocate-v4 -a habagou
flyctl ips allocate-v6 -a habagou
```

#### 4b. Configure DNS

DNS for `mattjmcnaughton.com` (including `habagou.mattjmcnaughton.com`) is
managed in [mattjmcnaughton/nuage](https://github.com/mattjmcnaughton/nuage)
— add or update records there (example:
[ac6a774](https://github.com/mattjmcnaughton/nuage/commit/ac6a774c7f8d3d2ba218a1c338c906aa838757b8)),
not in a registrar UI.

Pick one pattern (do not mix conflicting records for the same name):

| Hostname | Recommended records |
| -------- | ------------------- |
| Apex (`example.com`) | **A** → Fly IPv4 and **AAAA** → Fly IPv6 from `fly ips list` / `fly certs setup`. Prefer A/AAAA over CNAME at the apex unless your provider supports CNAME flattening (ANAME/ALIAS). |
| Subdomain (`habagou.mattjmcnaughton.com`) | **CNAME** → the unique `*.fly.dev` target shown by `fly certs setup` (typically `habagou.fly.dev`), **or** A/AAAA like the apex. |

Certificate issuance also needs domain validation via at least one of:

- AAAA pointing at the app (common with the recommended A/AAAA setup), or
- `_acme-challenge` CNAME (DNS-01; useful for wildcards or pre-traffic certs), or
- `_fly-ownership` TXT (ownership when behind a CDN/proxy).

Use exactly the values `fly certs setup` / the dashboard shows — do not invent
targets.

**Cloudflare (orange-cloud proxy):** set SSL/TLS mode to Full or Full (strict)
(not Flexible — redirect loops). Add the `_fly-ownership` TXT Fly shows so
ownership validates through the proxy. See
[Fly + Cloudflare](https://fly.io/docs/networking/understanding-cloudflare/).

#### 4c. Wait for the cert and verify

DNS propagation can take minutes to hours. Then:

```sh
flyctl certs check <custom-domain> -a habagou
flyctl certs list -a habagou
curl -fsSI https://<custom-domain>/readyz
just smoke BASE_URL=https://<custom-domain>
```

`fly certs check` reports validation progress. If it stalls, confirm there are
no conflicting A/AAAA/CNAME records, wait out Let's Encrypt rate limits if you
hammered failed validations, and retry.

### 5. Enable continuous deploy

Create a deploy token and store it in GitHub:

```sh
flyctl tokens create deploy -a habagou
# GitHub → Settings → Secrets and variables → Actions → New repository secret
# Name: FLY_API_TOKEN
# Value: <token from above>
```

After this, each successful release on `main` runs (in parallel) the `image`
and `deploy` jobs in `.github/workflows/release.yml`:

- `image`: build/push `ghcr.io/mattjmcnaughton/habagou:<version>`
- `deploy`: checkout the release tag → `flyctl deploy --app habagou --remote-only`

## Ongoing CD

1. Merge to `main`.
2. CI (`gate`, integration, e2e, …) succeeds.
3. Release workflow: semantic-release bumps version / tags / changelog.
4. In parallel:
   - `image` job builds and pushes `ghcr.io/mattjmcnaughton/habagou:<version>`.
   - `deploy` job checks out that tag and `flyctl deploy --remote-only` (Fly builds).
5. Fly release machine runs bootstrap once; app machines start with
   `HABAGOU_RUN_BOOTSTRAP=0`.

## Manual redeploy / rollback

```sh
# Redeploy current checkout / a checked-out tag (Fly rebuilds)
git checkout vX.Y.Z
flyctl deploy --app habagou --remote-only

# Or redeploy a previous Fly-built image (from fly releases --image)
flyctl deploy --app habagou --image registry.fly.io/habagou:<deployment-tag> --remote-only

# Inspect
flyctl releases -a habagou
flyctl logs -a habagou
```

## Troubleshooting

| Symptom | What to check |
| ------- | ------------- |
| `ModuleNotFoundError: No module named 'psycopg2'` during migrate | `DATABASE_URL` still uses Neon's `postgresql://…`. Rewrite to `postgresql+asyncpg://…` (and prefer `?ssl=require`). |
| `TypeError: … unexpected keyword argument 'sslmode'` / `'channel_binding'` | Neon libpq params. Use `?ssl=require` only — drop `sslmode` and `channel_binding`. (`config.py` normalizes once deployed.) |
| Release fails on migrate / `Connect call failed` | Neon cold start; wrong host/password; or secrets still **Staged** on a first deploy (use `--skip-release-command` then a full deploy — see §3). |
| `fly secrets deploy`: no machines available | Expected before the first successful Machine-creating deploy. Use `--skip-release-command` first, then `fly secrets deploy` if needed, then a full deploy. |
| App serves but empty data | Release machine may have failed bootstrap; check `flyctl releases` and logs. App machines intentionally skip bootstrap. |
| Cert stuck / invalid | `fly certs check <domain>`; DNS A/AAAA/CNAME match `fly certs setup`; no proxy misconfig; ownership TXT if using Cloudflare. |
| Scale-to-zero cold start | First request after idle wakes a machine; acceptable for this app. |

## Local Compose vs Fly

| | Compose | Fly app machines | Fly release machine |
| - | ------- | ---------------- | ------------------- |
| Bootstrap | Yes (`HABAGOU_RUN_BOOTSTRAP` defaults to 1) | No (`HABAGOU_RUN_BOOTSTRAP=0` in `fly.toml`) | Yes (`RELEASE_COMMAND=1`) |
| DB | Compose Postgres | Neon | Neon |
