"""OneDrive client for interacting with Microsoft Graph API.

Provides a typed interface for CRUD operations on files and folders
in OneDrive / SharePoint document libraries via the Microsoft Graph SDK.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from msgraph import GraphServiceClient
from msgraph.generated.models.drive_item import DriveItem
from msgraph.generated.models.folder import Folder

from maf_onedrive_integration.onedrive.models import DriveItemInfo, FolderInfo

if TYPE_CHECKING:
    from azure.core.credentials import TokenCredential
    from azure.core.credentials_async import AsyncTokenCredential

logger = logging.getLogger(__name__)

_DEFAULT_SCOPES: list[str] = ["https://graph.microsoft.com/.default"]


def _to_drive_item_info(item: DriveItem) -> DriveItemInfo:
    """Convert a Graph SDK ``DriveItem`` to our ``DriveItemInfo`` model."""
    return DriveItemInfo(
        id=item.id or "",
        name=item.name or "",
        size=item.size,
        mime_type=item.file.mime_type if item.file else None,
        is_folder=item.folder is not None,
        created_at=item.created_date_time,
        modified_at=item.last_modified_date_time,
        web_url=item.web_url,
        download_url=item.additional_data.get("@microsoft.graph.downloadUrl"),
    )


class OneDriveClient:
    """High-level client for OneDrive / SharePoint file operations.

    Parameters
    ----------
    credential:
        An ``azure-identity`` credential that implements ``TokenCredential``.
    scopes:
        OAuth 2.0 scopes.  Defaults to ``["https://graph.microsoft.com/.default"]``
        which is suitable for application-permission flows.
    graph_client:
        Optional pre-configured ``GraphServiceClient``.  When provided the
        *credential* and *scopes* arguments are ignored.  This is useful for
        testing and for advanced scenarios where the caller wants full control
        over the HTTP pipeline.
    """

    def __init__(
        self,
        credential: TokenCredential | AsyncTokenCredential | None = None,
        scopes: list[str] | None = None,
        *,
        graph_client: GraphServiceClient | None = None,
    ) -> None:
        if graph_client is not None:
            self._client = graph_client
        elif credential is not None:
            self._client = GraphServiceClient(
                credentials=credential,
                scopes=scopes or _DEFAULT_SCOPES,
            )
        else:
            msg = "Either 'credential' or 'graph_client' must be provided."
            raise ValueError(msg)

    # ------------------------------------------------------------------
    # Site / Drive helpers
    # ------------------------------------------------------------------

    async def get_site_drive_id(self, hostname: str, site_path: str) -> str:
        """Resolve the default document-library drive ID for a SharePoint site.

        Parameters
        ----------
        hostname:
            e.g. ``"contoso.sharepoint.com"``
        site_path:
            Server-relative path, e.g. ``"/sites/my-team"``
        """
        site = await self._client.sites.by_site_id(f"{hostname}:{site_path}").get()
        if site is None:
            msg = f"Site not found: {hostname}:{site_path}"
            raise FileNotFoundError(msg)

        drive = await self._client.sites.by_site_id(site.id or "").drive.get()
        if drive is None:
            msg = f"Default drive not found for site {hostname}:{site_path}"
            raise FileNotFoundError(msg)
        return drive.id or ""

    # ------------------------------------------------------------------
    # List / Read
    # ------------------------------------------------------------------

    async def list_items(
        self, drive_id: str, folder_id: str = "root"
    ) -> list[DriveItemInfo]:
        """List immediate children of a folder in a drive.

        Parameters
        ----------
        drive_id:
            The drive (document library) identifier.
        folder_id:
            The item ID of the folder.  Use ``"root"`` for the drive root.
        """
        result = await (
            self._client.drives.by_drive_id(drive_id)
            .items.by_drive_item_id(folder_id)
            .children.get()
        )
        if result is None or result.value is None:
            return []
        return [_to_drive_item_info(item) for item in result.value]

    async def list_items_by_path(self, drive_id: str, path: str) -> list[DriveItemInfo]:
        """List children of a folder identified by its path relative to the drive root.

        Parameters
        ----------
        drive_id:
            The drive (document library) identifier.
        path:
            Path relative to the drive root, e.g. ``"Documents/Reports"``.
        """
        # Resolve the folder first, then list children.
        folder_item = await (
            self._client.drives.by_drive_id(drive_id).root.item_with_path(path).get()
        )
        if folder_item is None:
            msg = f"Folder not found at path: {path}"
            raise FileNotFoundError(msg)
        return await self.list_items(drive_id, folder_item.id or "root")

    async def get_item(self, drive_id: str, item_id: str) -> DriveItemInfo:
        """Get metadata for a single drive item.

        Parameters
        ----------
        drive_id:
            The drive (document library) identifier.
        item_id:
            The drive item identifier.
        """
        item = await (
            self._client.drives.by_drive_id(drive_id)
            .items.by_drive_item_id(item_id)
            .get()
        )
        if item is None:
            msg = f"Item not found: {item_id}"
            raise FileNotFoundError(msg)
        return _to_drive_item_info(item)

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    async def download_file(
        self,
        drive_id: str,
        item_id: str,
        destination: str | Path,
    ) -> Path:
        """Download a file from OneDrive to the local filesystem.

        Parameters
        ----------
        drive_id:
            The drive (document library) identifier.
        item_id:
            The drive item identifier for the file.
        destination:
            Local path (file or directory).  If a directory, the remote
            file name is preserved.

        Returns
        -------
        Path
            The local path of the downloaded file.
        """
        destination = Path(destination)

        # If destination is a directory, resolve the filename from Graph.
        if destination.is_dir():
            meta = await self.get_item(drive_id, item_id)
            destination = destination / meta.name

        content: bytes | None = await (
            self._client.drives.by_drive_id(drive_id)
            .items.by_drive_item_id(item_id)
            .content.get()
        )
        if content is None:
            msg = f"No content returned for item {item_id}"
            raise FileNotFoundError(msg)

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        logger.info("Downloaded %s to %s", item_id, destination)
        return destination

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    async def upload_file(
        self,
        drive_id: str,
        parent_folder_id: str,
        filename: str,
        content: bytes,
    ) -> DriveItemInfo:
        """Upload (or replace) a small file (≤ 250 MB) into a folder.

        Parameters
        ----------
        drive_id:
            The drive (document library) identifier.
        parent_folder_id:
            The item ID of the destination folder.
        filename:
            The desired filename in OneDrive.
        content:
            Raw bytes of the file.

        Returns
        -------
        DriveItemInfo
            Metadata of the newly created / updated drive item.
        """
        # Use the Graph SDK to PUT raw bytes at the path-based content endpoint.
        result: DriveItem | None = await (
            self._client.drives.by_drive_id(drive_id)
            .items.by_drive_item_id(f"{parent_folder_id}:/{filename}:")
            .content.put(content)
        )
        if result is None:
            msg = f"Upload returned no metadata for {filename}"
            raise RuntimeError(msg)
        return _to_drive_item_info(result)

    async def upload_file_by_path(
        self,
        drive_id: str,
        remote_path: str,
        content: bytes,
    ) -> DriveItemInfo:
        """Upload (or replace) a file using a path relative to the drive root.

        Parameters
        ----------
        drive_id:
            The drive (document library) identifier.
        remote_path:
            Full path relative to root, e.g. ``"Documents/report.pdf"``.
        content:
            Raw bytes of the file.
        """
        result: DriveItem | None = await (
            self._client.drives.by_drive_id(drive_id)
            .root.item_with_path(remote_path)
            .content.put(content)
        )
        if result is None:
            msg = f"Upload returned no metadata for {remote_path}"
            raise RuntimeError(msg)
        return _to_drive_item_info(result)

    # ------------------------------------------------------------------
    # Create folder
    # ------------------------------------------------------------------

    async def create_folder(
        self,
        drive_id: str,
        parent_folder_id: str,
        folder_name: str,
    ) -> DriveItemInfo:
        """Create a new folder inside a parent folder.

        Parameters
        ----------
        drive_id:
            The drive (document library) identifier.
        parent_folder_id:
            Item ID of the parent folder (use ``"root"`` for the drive root).
        folder_name:
            Name of the new folder.
        """
        new_folder = DriveItem(
            name=folder_name,
            folder=Folder(),
            additional_data={"@microsoft.graph.conflictBehavior": "rename"},
        )
        result = await (
            self._client.drives.by_drive_id(drive_id)
            .items.by_drive_item_id(parent_folder_id)
            .children.post(new_folder)
        )
        if result is None:
            msg = f"Folder creation returned no metadata for {folder_name}"
            raise RuntimeError(msg)
        return _to_drive_item_info(result)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_item(self, drive_id: str, item_id: str) -> None:
        """Delete a file or folder (moves it to the recycle bin).

        Parameters
        ----------
        drive_id:
            The drive (document library) identifier.
        item_id:
            The drive item identifier to delete.
        """
        await (
            self._client.drives.by_drive_id(drive_id)
            .items.by_drive_item_id(item_id)
            .delete()
        )
        logger.info("Deleted item %s from drive %s", item_id, drive_id)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    async def get_folder_info(
        self, drive_id: str, folder_id: str = "root"
    ) -> FolderInfo:
        """Get folder metadata together with its children.

        Parameters
        ----------
        drive_id:
            The drive (document library) identifier.
        folder_id:
            The item ID of the folder.  Use ``"root"`` for the drive root.
        """
        folder_meta = await self.get_item(drive_id, folder_id)
        children = await self.list_items(drive_id, folder_id)
        return FolderInfo(
            id=folder_meta.id,
            name=folder_meta.name,
            children=children,
            web_url=folder_meta.web_url,
        )
