"""Sample script: authenticate with DefaultAzureCredential and download files.

Usage::

    # 1. Copy .env.example to .env and fill in real values.
    # 2. Ensure you have valid Azure credentials
    #    (e.g. ``az login`` or environment variables).
    # 3. Run:
    #        python -m maf_onedrive_integration.onedrive.sample_download

The script will:
  1. Resolve the default drive for the configured SharePoint site.
  2. List all files in the specified folder.
  3. Download every file to a local directory.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    """Entry point for the sample download script."""
    # ------------------------------------------------------------------ #
    # 1. Load configuration from .env
    # ------------------------------------------------------------------ #
    load_dotenv()

    hostname = os.environ.get("SHAREPOINT_HOSTNAME", "")
    site_path = os.environ.get("SHAREPOINT_SITE_PATH", "")
    folder_path = os.environ.get("ONEDRIVE_FOLDER_PATH", "")
    download_dir = Path(os.environ.get("DOWNLOAD_DIR", "./downloads"))

    if not hostname or not site_path:
        logger.error("SHAREPOINT_HOSTNAME and SHAREPOINT_SITE_PATH must be set in .env")
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # 2. Authenticate with DefaultAzureCredential
    # ------------------------------------------------------------------ #
    from azure.identity.aio import DefaultAzureCredential

    from maf_onedrive_integration.onedrive.client import OneDriveClient

    credential = DefaultAzureCredential()
    client = OneDriveClient(credential=credential)

    try:
        # -------------------------------------------------------------- #
        # 3. Resolve the drive ID of the SharePoint site
        # -------------------------------------------------------------- #
        logger.info("Resolving drive for %s%s …", hostname, site_path)
        drive_id = await client.get_site_drive_id(hostname, site_path)
        logger.info("Drive ID: %s", drive_id)

        # -------------------------------------------------------------- #
        # 4. List files in the target folder
        # -------------------------------------------------------------- #
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

        # -------------------------------------------------------------- #
        # 5. Download each file
        # -------------------------------------------------------------- #
        download_dir.mkdir(parents=True, exist_ok=True)
        for f in files:
            dest = await client.download_file(drive_id, f.id, download_dir)
            logger.info("  ✓ Saved %s", dest)

        logger.info("Done - %d file(s) downloaded to %s", len(files), download_dir)

    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
