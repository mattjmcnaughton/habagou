# Authentication

Habagou uses a server-side OpenID Connect (OIDC) login flow. The browser never
receives an access token for Habagou's API; the FastAPI app is the relying party
and protects its own API with a first-party session cookie.

## Strategy

- **Keycloak** is the deterministic local-development and browser-test provider.
  Its realm and `dev` test user are generated from the checked-in realm template.
- **Auth0** is the intended hosted production provider. It can provide the
  customer-facing login methods (including social connections) without adding an
  identity service to the Fly deployment.
- The application is not coupled to either provider. It discovers a
  standards-compliant OIDC provider from `OIDC_ISSUER` (or the optional
  `OIDC_METADATA_URL` override).

This separation is deliberate: changing provider configuration does not change
the user schema, API authentication, or frontend login flow.

## Login flow

1. The frontend links to `GET /auth/login`.
2. The backend uses OIDC discovery and redirects the browser to the configured
   provider. Authlib keeps the short-lived authorization transaction in the
   signed session cookie.
3. `GET /auth/callback` exchanges the authorization code, obtains the OIDC
   identity claims, and provisions or reuses the local user by the stable
   `(issuer, subject)` pair.
4. The callback stores only Habagou's local user UUID in the signed `session`
   cookie and redirects to `/`.
5. Protected `/api/v1` routes resolve that UUID to a local user. Missing,
   malformed, or stale sessions return `401`.

The local session deliberately does **not** contain upstream access tokens,
refresh tokens, or profile claims. The cookie is signed (not encrypted), so its
only stored value is the non-sensitive local UUID. It is `HttpOnly` and
`SameSite=Lax`; production also requires the `Secure` attribute.

## Identity and profile data

`iss` + `sub` is the sole stable identity key. `username`, display name, and
email are presentation data refreshed at login; they are not used to identify a
user. The claim mapping prefers `preferred_username`, then email, then the
provider subject for a username, and uses `name` for the display name.

When enabling a new provider or Auth0 connection, add a representative
identity-mapping test first. In particular, ensure the provider returns the
claims needed for a pleasant display name and username; an email may be absent
for some social connections.

## Admin users

Habagou has a single elevated user class: **admin**. Admin status is *derived,
not stored* — a non-guest user is an admin when their email's domain (the part
after the final `@`, compared exactly and case-insensitively; subdomains and
lookalike suffixes do not match) is listed in `ADMIN_EMAIL_DOMAINS` (default
`mattjmcnaughton.com`). See `habagou.authz.is_admin`.

Because the email is refreshed from the identity provider on every sign-in,
classification self-heals with no migration, role table, or management UI. The
trust anchor is the OIDC provider's `email` claim, and the claim mapping
enforces it: a token carrying `email_verified: false` has its email dropped
before it is stored (see `habagou.auth._oidc_identity`), so a self-signup with
an unverified admin-domain address can never classify as admin. Providers that
omit the flag entirely keep their email — acceptable for the first-party
Keycloak/Auth0 setups, but worth rechecking if a new connection is added.

What admins currently unlock: selecting the AI model used by the AI chats
(pack generation and conversational practice) — surfaced to the frontend via
`is_admin` on `GET /api/v1/auth/session` and the `models` list on the two
status probes, and enforced server-side by the draft/turn endpoints (403 for a
non-admin override, 422 off-allowlist).

## Provider configuration

| Setting | Purpose | Local / CI | Production with Auth0 |
| --- | --- | --- | --- |
| `OIDC_PROVIDER` | Display and client-registration name | `keycloak` | `auth0` |
| `OIDC_ISSUER` | Provider issuer used for discovery | local Keycloak realm | `https://<tenant>.auth0.com/` |
| `OIDC_CLIENT_ID` | OIDC web application client ID | `habagou` | Auth0 Regular Web Application client ID |
| `OIDC_CLIENT_SECRET` | OIDC web application client secret | generated local fixture value | Auth0 client secret |
| `OIDC_SCOPES` | Requested identity claims | `openid profile email` | `openid profile email` |
| `SESSION_SECRET_KEY` | Signs the local session cookie | checkout-derived dev value | random Fly secret |
| `SESSION_COOKIE_SECURE` | Requires HTTPS for the session cookie | `false` | `true` |

`OIDC_METADATA_URL` is normally unset. Set it only when a compliant provider's
discovery URL differs from `<issuer>/.well-known/openid-configuration`.

## Local development and CI

`devenv` starts Keycloak on the checkout's derived port and imports the rendered
realm. `just test-e2e` expects that issuer to be available. GitHub Actions
starts the same Keycloak image, renders the same realm file, and waits for its
discovery endpoint before it runs Playwright.

The browser e2e helper signs in with the realm's local `dev` account. This
keeps the test suite independent of Auth0 credentials, network access, and
tenant state.

## Logout and session lifetime

`POST /auth/logout` clears Habagou's local session cookie. It intentionally
does not log the browser out of the upstream identity provider. A subsequent
login may therefore complete immediately if the provider still has a session.
Provider-initiated logout, backchannel logout, token refresh, and server-side
session revocation are deferred until the product needs them.

## Operational checklist

- Use an Auth0 **Regular Web Application**, not an SPA application.
- Register `https://<public-host>/auth/callback` as an Auth0 Allowed Callback
  URL.
- Configure the production settings before the first Fly deploy; see
  [deploy.md](deploy.md#auth0-configuration).
- Rotate `SESSION_SECRET_KEY` to invalidate every existing Habagou session.
- If email becomes a security-sensitive channel, require and check the
  provider's verified-email claim before relying on it.
