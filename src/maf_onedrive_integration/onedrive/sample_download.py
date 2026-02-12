"""Sample script: download files from a SharePoint site.

Usage::

    # 1. Ensure you have valid Azure credentials
    #    (e.g. ``az login`` or environment variables).
    # 2. Run:
    #        python -m maf_onedrive_integration.onedrive.sample_download

The script will:
  1. Prompt for the SharePoint hostname and site path.
  2. Optionally prompt for a folder path within the document library.
  3. Download every file to a local ``./downloads`` directory.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

DOWNLOAD_DIR = Path("./downloads")


def _prompt(label: str, default: str = "") -> str:
    """Prompt the user for input, showing a default value if available."""
    if default:
        value = input(f"{label} [{default}]: ").strip()
        return value or default
    while True:
        value = input(f"{label}: ").strip()
        if value:
            return value
        print(f"  ⚠  {label} is required.")


async def main() -> None:
    """Entry point for the sample download script."""

    print("\n── SharePoint / OneDrive download sample ──\n")

    hostname = _prompt("SharePoint hostname (e.g. contoso.sharepoint.com)")
    if "." not in hostname:
        hostname = f"{hostname}.sharepoint.com"
    site_path = _prompt("Site path (e.g. /sites/my-team)")
    if not site_path.startswith("/"):
        site_path = f"/{site_path}"
    folder_path = input("Folder path (leave empty for root): ").strip()

    from azure.identity.aio import DefaultAzureCredential

    from maf_onedrive_integration.onedrive.client import OneDriveClient

    credential = DefaultAzureCredential()
    client = OneDriveClient(credential=credential)

    try:
        logger.info("Resolving drive for %s%s …", hostname, site_path)
        drive_id = await client.get_site_drive_id(hostname, site_path)
        logger.info("Drive ID: %s", drive_id)

        if folder_path:
            logger.info("Listing files in /%s …", folder_path)
            items = await client.list_items_by_path(drive_id, folder_path)
        else:
            logger.info("Listing files in the drive root …")
            items = await client.list_items(drive_id)

        files = [item for item in items if item.is_file]
        logger.info("Found %d file(s):", len(files))
        for f in files:
            logger.info("  • %s  (%s bytes)", f.name, f.size)

        if not files:
            logger.info("Nothing to download.")
            return

        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        for f in files:
            dest = await client.download_file(drive_id, f.id, DOWNLOAD_DIR)
            logger.info("  ✓ Saved %s", dest)

        logger.info("Done - %d file(s) downloaded to %s", len(files), DOWNLOAD_DIR)

    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
