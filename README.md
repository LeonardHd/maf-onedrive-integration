# maf-onedrive-integration

MAF OneDrive Integration

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

## Setup

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and sync
git clone <repo-url> && cd maf-onedrive-integration
uv sync
```

This installs the package in **editable mode** — any changes to source files under `src/` are reflected immediately.

## Usage

```bash
# Run via CLI entry point
uv run maf-onedrive-integration

# Run the module directly
uv run python -m maf_onedrive_integration.example_app
```

## Downloading Files from OneDrive / SharePoint

The included sample script authenticates with Azure and downloads all files from a SharePoint document library folder to your local machine.

### 1. Azure App Registration

Your Azure AD app registration needs the following **API permissions** on Microsoft Graph:

- `Sites.Read.All` (application) — or `Files.Read.All` for broader access
- Grant admin consent in the Azure portal

### 2. Authenticate

The script uses [`DefaultAzureCredential`](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.defaultazurecredential), which tries multiple credential sources in order. The simplest options:

| Method | How |
|---|---|
| **Azure CLI** | Run `az login` before the script |
| **Environment variables** | Set `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` |
| **Managed Identity** | Works automatically on Azure-hosted compute |

### 3. Configure `.env`

```bash
cp .env.example .env
```

Edit `.env` with your SharePoint details:

```dotenv
SHAREPOINT_HOSTNAME=contoso.sharepoint.com
SHAREPOINT_SITE_PATH=/sites/my-team
ONEDRIVE_FOLDER_PATH=General          # folder inside the document library (empty = root)
DOWNLOAD_DIR=./downloads              # local destination
```

### 4. Run

```bash
uv run python -m maf_onedrive_integration.onedrive.sample_download
```

The script will:

1. Resolve the default drive for the configured SharePoint site
2. List all files in the specified folder
3. Download each file to `DOWNLOAD_DIR`

## Adding Dependencies

```bash
uv add <package>          # Add a runtime dependency
uv add --dev <package>    # Add a dev dependency
```

## Development

```bash
uv sync                   # Sync environment with lockfile
uv run <command>          # Run a command in the project venv
uv lock                   # Re-resolve and update the lockfile
```
