# maf-onedrive-integration

A FastAPI web application that lets users sign in with their Microsoft account
and browse their OneDrive files.

## Authentication

This application needs delegated access to Microsoft Graph (OneDrive / SharePoint) on behalf of a signed-in user. There are two viable OAuth 2.0 flows for this, and the choice depends on where the token acquisition happens.

### Option 1 — Authorization Code Flow (current implementation)

The backend drives the entire OAuth exchange:

1. The user clicks **Sign in** and is redirected to Azure AD's `/authorize` endpoint.
2. Azure AD redirects back to `/auth/callback` with an **authorization code**.
3. The backend redeems the code for tokens using `azure.identity.AuthorizationCodeCredential` (which also handles token refresh transparently).
4. The credential object is stored **server-side** in a dict keyed by a random session ID. Only that session ID is written into an encrypted cookie via Starlette's `SessionMiddleware`.

Because the tokens never leave the server, this is the more secure option and the recommended pattern when the frontend is a server-rendered or backend-served page (as is the case here — `index.html` is served by FastAPI as a static file).

**Trade-off:** the backend must maintain a session store (`_credentials` dict today, Redis / a database in production) so it can map cookies back to credentials. Scaling horizontally requires a shared session store or sticky sessions.

```
Browser                  FastAPI backend              Azure AD
  │                           │                          │
  │  GET /login               │                          │
  │ ────────────────────────> │                          │
  │  302 → authorize URL      │                          │
  │ <──────────────────────── │                          │
  │                           │                          │
  │  User authenticates       │                          │
  │ ─────────────────────────────────────────────────>   │
  │  302 → /auth/callback?code=…                         │
  │ <─────────────────────────────────────────────────   │
  │                           │                          │
  │  GET /auth/callback       │                          │
  │ ────────────────────────> │                          │
  │                           │  POST /token (code)      │
  │                           │ ────────────────────-->  │
  │                           │  access + refresh token  │
  │                           │ <──────────────────────  │
  │                           │                          │
  │  Set-Cookie: session_id   │  store credential by sid │
  │ <──────────────────────── │                          │
```

### Option 2 — On-Behalf-Of (OBO) Flow

If the frontend were turned into a true **Single-Page Application** (SPA) that acquires its own tokens (e.g. using MSAL.js), the architecture would shift:

1. The SPA uses MSAL.js to sign the user in and obtain an **access token** scoped to the backend's API (a custom scope such as `api://<backend-client-id>/access_as_user`).
2. Every API call to the FastAPI backend includes that token in the `Authorization: Bearer …` header.
3. The backend validates the incoming token and then exchanges it for a **Microsoft Graph token** using the [OBO flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow) (`ConfidentialClientApplication.acquire_token_on_behalf_of` in MSAL Python).
4. The Graph token is used to call OneDrive / SharePoint APIs on behalf of the user.

**Trade-off:** no server-side session store is needed (the SPA manages its own token cache), but the access token is exposed to the browser. The backend's Azure AD app registration must expose an API and configure the `knownClientApplications` / `api` permissions accordingly.

```
Browser (SPA + MSAL.js)        FastAPI backend              Azure AD
  │                                 │                          │
  │  MSAL.js acquireTokenSilent     │                          │
  │ ──────────────────────────────────────────────────────-->  │
  │  access token (audience=backend)│                          │
  │ <────────────────────────────────────────────────────────  │
  │                                 │                          │
  │  GET /api/files                 │                          │
  │  Authorization: Bearer <token>  │                          │
  │ ──────────────────────────────> │                          │
  │                                 │  OBO: exchange token     │
  │                                 │  for Graph access token  │
  │                                 │ ────────────────────-->  │
  │                                 │  Graph access token      │
  │                                 │ <──────────────────────  │
  │                                 │                          │
  │  JSON response                  │  call Graph API          │
  │ <────────────────────────────── │                          │
```

### Which to choose?

| Concern | Auth Code (Option 1) | OBO (Option 2) |
|---|---|---|
| Token location | Server only | Browser + server |
| Session store required | Yes | No |
| Frontend complexity | Minimal (static HTML) | Higher (MSAL.js, token management) |
| Horizontal scaling | Needs shared sessions | Stateless backend |
| Azure AD registration | Standard web app | Expose an API + configure OBO |

This project currently implements **Option 1** because the frontend is a simple static page served by the backend.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- An Azure AD app registration (see below)

## Azure AD App Registration

1. Go to the [Azure Portal → App registrations](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade) and click **New registration**.
2. Set a name (e.g. *MAF OneDrive Browser*).
3. Under **Redirect URIs**, add `http://localhost:8000/auth/callback` (type *Web*).
4. After creation, go to **Certificates & secrets → New client secret** and copy the value.
5. Under **API permissions**, add the following **Delegated** permissions:
   * Graph API:
    - `User.Read`
   * SharePoint API:
    - `AllSites.Read`
6. Click **Grant admin consent** (or let each user consent individually).

Copy the **Application (client) ID** and the **Client secret value** — you will
put them in the `.env` file.

## Configuration

```bash
cp .env.example .env
```

Edit `.env` with your Azure AD credentials:

```dotenv
APPLICATION_ID=<your-application-client-id>
APPLICATION_SECRET=<your-client-secret>
TENANT_ID=common                                   # or a specific tenant ID
REDIRECT_URI=http://localhost:8000/auth/callback
SESSION_SECRET=<random-string>
```

## Setup

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and sync (installs all dependencies including dev tools)
git clone <repo-url> && cd maf-onedrive-integration
uv sync --all-extras
```

## Running the Web Application

```bash
uv run maf-onedrive-web
# or
uv run uvicorn maf_onedrive_integration.app:app --reload
```

Then open <http://localhost:8000> in your browser, sign in with your Microsoft
account, and browse your OneDrive files.

## Development

### Install dev dependencies

```bash
uv sync --all-extras
```

### Linting & formatting

```bash
uv run ruff check .          # lint
uv run ruff format .         # auto-format
```

### Type checking

```bash
uv run ty check
```

### Testing

```bash
uv run pytest                # run all tests
uv run pytest -v             # verbose output
```

### Pre-commit hooks

```bash
uv run pre-commit install    # install hooks (once)
uv run pre-commit run --all-files  # run manually
```

The hooks run **ruff** (lint + format) and basic file checks (trailing
whitespace, YAML/TOML validity) on every commit.

## Downloading Files (CLI script)

The included sample script authenticates with Azure and downloads all files
from a SharePoint document library folder to your local machine.
See the SharePoint configuration variables in `.env.example` and run:

```bash
uv run python -m maf_onedrive_integration.onedrive.sample_download
```
