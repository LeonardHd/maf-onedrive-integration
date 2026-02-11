"""Tests for OneDrive client."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from msgraph.generated.models.drive import Drive
from msgraph.generated.models.drive_item import DriveItem
from msgraph.generated.models.drive_item_collection_response import (
    DriveItemCollectionResponse,
)
from msgraph.generated.models.file import File
from msgraph.generated.models.folder import Folder
from msgraph.generated.models.site import Site

from maf_onedrive_integration.onedrive.client import OneDriveClient
from maf_onedrive_integration.onedrive.models import DriveItemInfo

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_drive_item(
    *,
    item_id: str = "item-1",
    name: str = "report.pdf",
    size: int = 1024,
    is_folder: bool = False,
    mime_type: str = "application/pdf",
) -> DriveItem:
    """Create a fake DriveItem for testing."""
    item = DriveItem()
    item.id = item_id
    item.name = name
    item.size = size
    item.web_url = f"https://contoso.sharepoint.com/items/{item_id}"
    item.created_date_time = datetime(2025, 1, 1, tzinfo=UTC)
    item.last_modified_date_time = datetime(2025, 6, 1, tzinfo=UTC)
    item.additional_data = {}
    if is_folder:
        item.folder = Folder()
        item.file = None
    else:
        item.file = File()
        item.file.mime_type = mime_type
        item.folder = None
    return item


def _graph_client_mock() -> MagicMock:
    """Return a deeply-patched ``GraphServiceClient`` mock."""
    return MagicMock()


# ---------------------------------------------------------------------------
# Tests: __init__
# ---------------------------------------------------------------------------


class TestOneDriveClientInit:
    """Constructor validation."""

    def test_raises_without_credential_or_client(self) -> None:
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="Either 'credential' or 'graph_client'"):
            OneDriveClient()

    def test_accepts_graph_client(self) -> None:
        # Arrange
        mock_client = _graph_client_mock()

        # Act
        client = OneDriveClient(graph_client=mock_client)

        # Assert
        assert client._client is mock_client

    @patch("maf_onedrive_integration.onedrive.client.GraphServiceClient")
    def test_creates_graph_client_from_credential(
        self, mock_graph_cls: MagicMock
    ) -> None:
        # Arrange
        mock_cred = MagicMock()

        # Act
        OneDriveClient(credential=mock_cred)

        # Assert
        mock_graph_cls.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: list_items
# ---------------------------------------------------------------------------


class TestListItems:
    """list_items returns converted DriveItemInfo objects."""

    @pytest.fixture()
    def client(self) -> OneDriveClient:
        mock = _graph_client_mock()
        return OneDriveClient(graph_client=mock)

    @pytest.mark.asyncio
    async def test_list_items_returns_files(self, client: OneDriveClient) -> None:
        # Arrange
        file1 = _make_drive_item(item_id="f1", name="a.txt", size=10)
        file2 = _make_drive_item(item_id="f2", name="b.txt", size=20)
        response = DriveItemCollectionResponse()
        response.value = [file1, file2]

        children_mock = AsyncMock(return_value=response)
        (
            client._client.drives.by_drive_id.return_value.items.by_drive_item_id.return_value.children.get
        ) = children_mock

        # Act
        result = await client.list_items("drive-1", "root")

        # Assert
        assert len(result) == 2
        assert result[0].id == "f1"
        assert result[0].name == "a.txt"
        assert result[1].id == "f2"

    @pytest.mark.asyncio
    async def test_list_items_empty(self, client: OneDriveClient) -> None:
        # Arrange
        response = DriveItemCollectionResponse()
        response.value = []

        children_mock = AsyncMock(return_value=response)
        (
            client._client.drives.by_drive_id.return_value.items.by_drive_item_id.return_value.children.get
        ) = children_mock

        # Act
        result = await client.list_items("drive-1")

        # Assert
        assert result == []

    @pytest.mark.asyncio
    async def test_list_items_none_response(self, client: OneDriveClient) -> None:
        # Arrange
        children_mock = AsyncMock(return_value=None)
        (
            client._client.drives.by_drive_id.return_value.items.by_drive_item_id.return_value.children.get
        ) = children_mock

        # Act
        result = await client.list_items("drive-1")

        # Assert
        assert result == []


# ---------------------------------------------------------------------------
# Tests: list_items_by_path
# ---------------------------------------------------------------------------


class TestListItemsByPath:
    """list_items_by_path resolves a folder, then lists children."""

    @pytest.fixture()
    def client(self) -> OneDriveClient:
        mock = _graph_client_mock()
        return OneDriveClient(graph_client=mock)

    @pytest.mark.asyncio
    async def test_list_items_by_path_success(self, client: OneDriveClient) -> None:
        # Arrange — mock folder resolution
        folder = _make_drive_item(item_id="folder-1", name="Reports", is_folder=True)
        folder_get = AsyncMock(return_value=folder)
        (
            client._client.drives.by_drive_id.return_value.root.item_with_path.return_value.get
        ) = folder_get

        # Arrange — mock children
        child = _make_drive_item(item_id="c1", name="report.pdf")
        response = DriveItemCollectionResponse()
        response.value = [child]
        children_get = AsyncMock(return_value=response)
        (
            client._client.drives.by_drive_id.return_value.items.by_drive_item_id.return_value.children.get
        ) = children_get

        # Act
        result = await client.list_items_by_path("drive-1", "Documents/Reports")

        # Assert
        assert len(result) == 1
        assert result[0].name == "report.pdf"

    @pytest.mark.asyncio
    async def test_list_items_by_path_not_found(self, client: OneDriveClient) -> None:
        # Arrange
        folder_get = AsyncMock(return_value=None)
        (
            client._client.drives.by_drive_id.return_value.root.item_with_path.return_value.get
        ) = folder_get

        # Act & Assert
        with pytest.raises(FileNotFoundError, match="Folder not found"):
            await client.list_items_by_path("drive-1", "nonexistent")


# ---------------------------------------------------------------------------
# Tests: get_item
# ---------------------------------------------------------------------------


class TestGetItem:
    @pytest.fixture()
    def client(self) -> OneDriveClient:
        mock = _graph_client_mock()
        return OneDriveClient(graph_client=mock)

    @pytest.mark.asyncio
    async def test_get_item_returns_info(self, client: OneDriveClient) -> None:
        # Arrange
        item = _make_drive_item(item_id="x1", name="photo.jpg", size=2048)
        get_mock = AsyncMock(return_value=item)
        (
            client._client.drives.by_drive_id.return_value.items.by_drive_item_id.return_value.get
        ) = get_mock

        # Act
        result = await client.get_item("drive-1", "x1")

        # Assert
        assert result.id == "x1"
        assert result.name == "photo.jpg"
        assert result.size == 2048
        assert result.is_file is True

    @pytest.mark.asyncio
    async def test_get_item_not_found(self, client: OneDriveClient) -> None:
        # Arrange
        get_mock = AsyncMock(return_value=None)
        (
            client._client.drives.by_drive_id.return_value.items.by_drive_item_id.return_value.get
        ) = get_mock

        # Act & Assert
        with pytest.raises(FileNotFoundError, match="Item not found"):
            await client.get_item("drive-1", "missing")


# ---------------------------------------------------------------------------
# Tests: download_file
# ---------------------------------------------------------------------------


class TestDownloadFile:
    @pytest.fixture()
    def client(self) -> OneDriveClient:
        mock = _graph_client_mock()
        return OneDriveClient(graph_client=mock)

    @pytest.mark.asyncio
    async def test_download_to_file(
        self, client: OneDriveClient, tmp_path: Path
    ) -> None:
        # Arrange
        dest = tmp_path / "downloaded.pdf"
        content_mock = AsyncMock(return_value=b"PDF-CONTENT")
        (
            client._client.drives.by_drive_id.return_value.items.by_drive_item_id.return_value.content.get
        ) = content_mock

        # Act
        result = await client.download_file("drive-1", "item-1", dest)

        # Assert
        assert result == dest
        assert dest.read_bytes() == b"PDF-CONTENT"

    @pytest.mark.asyncio
    async def test_download_to_directory(
        self, client: OneDriveClient, tmp_path: Path
    ) -> None:
        # Arrange — metadata lookup for filename
        item = _make_drive_item(item_id="item-1", name="report.pdf")
        get_mock = AsyncMock(return_value=item)
        (
            client._client.drives.by_drive_id.return_value.items.by_drive_item_id.return_value.get
        ) = get_mock

        # Arrange — content
        content_mock = AsyncMock(return_value=b"DATA")
        (
            client._client.drives.by_drive_id.return_value.items.by_drive_item_id.return_value.content.get
        ) = content_mock

        # Act
        result = await client.download_file("drive-1", "item-1", tmp_path)

        # Assert
        assert result == tmp_path / "report.pdf"
        assert result.read_bytes() == b"DATA"

    @pytest.mark.asyncio
    async def test_download_no_content_raises(
        self, client: OneDriveClient, tmp_path: Path
    ) -> None:
        # Arrange
        dest = tmp_path / "out.bin"
        content_mock = AsyncMock(return_value=None)
        (
            client._client.drives.by_drive_id.return_value.items.by_drive_item_id.return_value.content.get
        ) = content_mock

        # Act & Assert
        with pytest.raises(FileNotFoundError, match="No content"):
            await client.download_file("drive-1", "item-1", dest)


# ---------------------------------------------------------------------------
# Tests: upload_file_by_path
# ---------------------------------------------------------------------------


class TestUploadFileByPath:
    @pytest.fixture()
    def client(self) -> OneDriveClient:
        mock = _graph_client_mock()
        return OneDriveClient(graph_client=mock)

    @pytest.mark.asyncio
    async def test_upload_file_by_path_success(self, client: OneDriveClient) -> None:
        # Arrange
        uploaded = _make_drive_item(item_id="new-1", name="data.csv", size=999)
        put_mock = AsyncMock(return_value=uploaded)
        (
            client._client.drives.by_drive_id.return_value.root.item_with_path.return_value.content.put
        ) = put_mock

        # Act
        result = await client.upload_file_by_path(
            "drive-1", "Folder/data.csv", b"csv-content"
        )

        # Assert
        assert result.id == "new-1"
        assert result.name == "data.csv"

    @pytest.mark.asyncio
    async def test_upload_file_by_path_none_raises(
        self, client: OneDriveClient
    ) -> None:
        # Arrange
        put_mock = AsyncMock(return_value=None)
        (
            client._client.drives.by_drive_id.return_value.root.item_with_path.return_value.content.put
        ) = put_mock

        # Act & Assert
        with pytest.raises(RuntimeError, match="Upload returned no metadata"):
            await client.upload_file_by_path("drive-1", "f.txt", b"data")


# ---------------------------------------------------------------------------
# Tests: create_folder
# ---------------------------------------------------------------------------


class TestCreateFolder:
    @pytest.fixture()
    def client(self) -> OneDriveClient:
        mock = _graph_client_mock()
        return OneDriveClient(graph_client=mock)

    @pytest.mark.asyncio
    async def test_create_folder_success(self, client: OneDriveClient) -> None:
        # Arrange
        created = _make_drive_item(
            item_id="folder-new", name="NewFolder", is_folder=True
        )
        post_mock = AsyncMock(return_value=created)
        (
            client._client.drives.by_drive_id.return_value.items.by_drive_item_id.return_value.children.post
        ) = post_mock

        # Act
        result = await client.create_folder("drive-1", "root", "NewFolder")

        # Assert
        assert result.id == "folder-new"
        assert result.name == "NewFolder"
        assert result.is_folder is True


# ---------------------------------------------------------------------------
# Tests: delete_item
# ---------------------------------------------------------------------------


class TestDeleteItem:
    @pytest.fixture()
    def client(self) -> OneDriveClient:
        mock = _graph_client_mock()
        return OneDriveClient(graph_client=mock)

    @pytest.mark.asyncio
    async def test_delete_item_calls_delete(self, client: OneDriveClient) -> None:
        # Arrange
        delete_mock = AsyncMock(return_value=None)
        (
            client._client.drives.by_drive_id.return_value.items.by_drive_item_id.return_value.delete
        ) = delete_mock

        # Act
        await client.delete_item("drive-1", "item-1")

        # Assert
        delete_mock.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests: get_site_drive_id
# ---------------------------------------------------------------------------


class TestGetSiteDriveId:
    @pytest.fixture()
    def client(self) -> OneDriveClient:
        mock = _graph_client_mock()
        return OneDriveClient(graph_client=mock)

    @pytest.mark.asyncio
    async def test_get_site_drive_id_success(self, client: OneDriveClient) -> None:
        # Arrange — site lookup
        site = Site()
        site.id = "site-123"
        site_get = AsyncMock(return_value=site)
        client._client.sites.by_site_id.return_value.get = site_get

        # Arrange — drive lookup
        drive = Drive()
        drive.id = "drive-abc"
        drive_get = AsyncMock(return_value=drive)
        client._client.sites.by_site_id.return_value.drive.get = drive_get

        # Act
        result = await client.get_site_drive_id("contoso.sharepoint.com", "/sites/team")

        # Assert
        assert result == "drive-abc"

    @pytest.mark.asyncio
    async def test_get_site_drive_id_site_not_found(
        self, client: OneDriveClient
    ) -> None:
        # Arrange
        site_get = AsyncMock(return_value=None)
        client._client.sites.by_site_id.return_value.get = site_get

        # Act & Assert
        with pytest.raises(FileNotFoundError, match="Site not found"):
            await client.get_site_drive_id("contoso.sharepoint.com", "/sites/missing")


# ---------------------------------------------------------------------------
# Tests: models
# ---------------------------------------------------------------------------


class TestDriveItemInfo:
    def test_is_file_property(self) -> None:
        # Arrange
        info = DriveItemInfo(id="1", name="file.txt", is_folder=False)

        # Act & Assert
        assert info.is_file is True
        assert info.is_folder is False

    def test_is_folder_property(self) -> None:
        # Arrange
        info = DriveItemInfo(id="2", name="Folder", is_folder=True)

        # Act & Assert
        assert info.is_file is False
        assert info.is_folder is True

    def test_frozen(self) -> None:
        # Arrange
        info = DriveItemInfo(id="1", name="file.txt")

        # Act & Assert
        with pytest.raises(AttributeError):
            info.name = "changed"  # type: ignore[misc]
