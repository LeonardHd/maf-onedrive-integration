# maf-onedrive-integration

A FastAPI web application that lets users sign in with their Microsoft account
and browse their OneDrive files.

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
