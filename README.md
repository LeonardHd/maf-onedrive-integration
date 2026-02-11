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
