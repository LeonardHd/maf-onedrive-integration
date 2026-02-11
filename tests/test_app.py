"""Tests for the FastAPI web application."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import maf_onedrive_integration.app as app_module
from maf_onedrive_integration.app import app
from maf_onedrive_integration.onedrive.models import DriveItemInfo, SiteInfo
from maf_onedrive_integration.summary_agent.agent import SummaryResult

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture(autouse=True)
def _reset_credentials() -> Generator[None]:
    """Ensure the credential store is cleared between tests."""
    app_module._credentials.clear()
    yield
    app_module._credentials.clear()


def _login_mocks() -> MagicMock:
    """Return a mock credential whose ``get_token`` is a no-op."""
    mock_credential = MagicMock()
    mock_credential.get_token.return_value = MagicMock(token="tok", expires_on=0)
    return mock_credential


class TestIndex:
    async def test_returns_html(self) -> None:
        # Arrange
        transport = ASGITransport(app=app)

        # Act
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")

        # Assert
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestLogin:
    @patch("maf_onedrive_integration.app.urlencode", return_value="mocked=params")
    async def test_redirects_to_azure_ad(self, _mock_urlencode: MagicMock) -> None:
        # Arrange
        transport = ASGITransport(app=app)

        # Act
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/login")

        # Assert
        assert response.status_code == 307
        assert "login.microsoftonline.com" in response.headers["location"]
        assert "/oauth2/v2.0/authorize" in response.headers["location"]


class TestAuthCallback:
    @patch("maf_onedrive_integration.app.OneDriveClient")
    @patch("maf_onedrive_integration.app.AuthorizationCodeCredential")
    async def test_successful_callback_sets_session(
        self, mock_cred_cls: MagicMock, mock_client_cls: MagicMock
    ) -> None:
        # Arrange
        mock_cred_cls.return_value = _login_mocks()

        mock_client = AsyncMock()
        mock_client.get_user_display_name.return_value = "Test User"
        mock_client_cls.return_value = mock_client

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Act
            callback_resp = await client.get("/auth/callback?code=auth-code-456")
            me_resp = await client.get("/api/me")

        # Assert
        assert callback_resp.status_code == 307
        assert me_resp.status_code == 200
        assert me_resp.json()["name"] == "Test User"

    @patch("maf_onedrive_integration.app.OneDriveClient")
    @patch("maf_onedrive_integration.app.AuthorizationCodeCredential")
    async def test_callback_error_returns_400(
        self, mock_cred_cls: MagicMock, mock_client_cls: MagicMock
    ) -> None:
        # Arrange
        mock_cred_cls.return_value = MagicMock()

        mock_client = AsyncMock()
        mock_client.get_user_display_name.side_effect = RuntimeError("auth failed")
        mock_client_cls.return_value = mock_client

        transport = ASGITransport(app=app)

        # Act
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/auth/callback?code=bad-code")

        # Assert
        assert response.status_code == 400
        assert response.json()["error"] == "authentication_failed"

    async def test_callback_without_code_redirects_home(self) -> None:
        # Arrange
        transport = ASGITransport(app=app)

        # Act
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/auth/callback")

        # Assert
        assert response.status_code == 307
        assert response.headers["location"] == "/"


class TestLogout:
    @patch("maf_onedrive_integration.app.OneDriveClient")
    @patch("maf_onedrive_integration.app.AuthorizationCodeCredential")
    async def test_clears_session(
        self, mock_cred_cls: MagicMock, mock_client_cls: MagicMock
    ) -> None:
        # Arrange
        mock_cred_cls.return_value = _login_mocks()

        mock_client = AsyncMock()
        mock_client.get_user_display_name.return_value = "Test User"
        mock_client_cls.return_value = mock_client

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/auth/callback?code=test-code")

            # Act
            await client.get("/logout")
            me_resp = await client.get("/api/me")

        # Assert
        assert me_resp.status_code == 401


class TestApiMe:
    async def test_unauthenticated_returns_401(self) -> None:
        # Arrange
        transport = ASGITransport(app=app)

        # Act
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/me")

        # Assert
        assert response.status_code == 401
        assert response.json()["error"] == "Not authenticated"

    @patch("maf_onedrive_integration.app.OneDriveClient")
    @patch("maf_onedrive_integration.app.AuthorizationCodeCredential")
    async def test_authenticated_returns_user_name(
        self, mock_cred_cls: MagicMock, mock_client_cls: MagicMock
    ) -> None:
        # Arrange
        mock_cred_cls.return_value = _login_mocks()

        mock_client = AsyncMock()
        mock_client.get_user_display_name.return_value = "Alice"
        mock_client_cls.return_value = mock_client

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/auth/callback?code=c")

            # Act
            response = await client.get("/api/me")

        # Assert
        assert response.status_code == 200
        assert response.json()["name"] == "Alice"


class TestApiFiles:
    async def test_unauthenticated_returns_401(self) -> None:
        # Arrange
        transport = ASGITransport(app=app)

        # Act
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/files")

        # Assert
        assert response.status_code == 401

    @patch("maf_onedrive_integration.app.OneDriveClient")
    @patch("maf_onedrive_integration.app.AuthorizationCodeCredential")
    async def test_returns_file_list(
        self, mock_cred_cls: MagicMock, mock_client_cls: MagicMock
    ) -> None:
        # Arrange
        mock_cred_cls.return_value = _login_mocks()

        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_user_display_name.return_value = "User"
        mock_client.get_my_drive_id.return_value = "drive-123"
        mock_client.list_items.return_value = [
            DriveItemInfo(
                id="item-1",
                name="report.pdf",
                size=2048,
                mime_type="application/pdf",
                is_folder=False,
                modified_at=datetime(2025, 6, 1, tzinfo=UTC),
            ),
            DriveItemInfo(
                id="item-2",
                name="Documents",
                is_folder=True,
            ),
        ]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/auth/callback?code=test-code")

            # Act
            response = await client.get("/api/files")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["name"] == "report.pdf"
        assert data[0]["is_folder"] is False
        assert data[0]["size"] == 2048
        assert data[1]["name"] == "Documents"
        assert data[1]["is_folder"] is True

    @patch("maf_onedrive_integration.app.OneDriveClient")
    @patch("maf_onedrive_integration.app.AuthorizationCodeCredential")
    async def test_returns_files_by_path(
        self, mock_cred_cls: MagicMock, mock_client_cls: MagicMock
    ) -> None:
        # Arrange
        mock_cred_cls.return_value = _login_mocks()

        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_user_display_name.return_value = "User"
        mock_client.get_my_drive_id.return_value = "drive-123"
        mock_client.list_items_by_path.return_value = [
            DriveItemInfo(id="item-3", name="notes.txt", size=512),
        ]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/auth/callback?code=test-code")

            # Act
            response = await client.get("/api/files?path=Documents")

        # Assert
        assert response.status_code == 200
        mock_client.list_items_by_path.assert_called_once_with("drive-123", "Documents")

    @patch("maf_onedrive_integration.app.OneDriveClient")
    @patch("maf_onedrive_integration.app.AuthorizationCodeCredential")
    async def test_graph_api_error_returns_502(
        self, mock_cred_cls: MagicMock, mock_client_cls: MagicMock
    ) -> None:
        # Arrange
        mock_cred_cls.return_value = _login_mocks()

        call_count = 0
        mock_client = AsyncMock()
        mock_client.get_user_display_name.return_value = "User"

        def make_client(**kwargs: object) -> AsyncMock:
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                # Second call (from /api/files) - simulate failure
                mock_client.get_my_drive_id.side_effect = RuntimeError("API error")
            return mock_client

        mock_client_cls.side_effect = make_client

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/auth/callback?code=test-code")

            # Act
            response = await client.get("/api/files")

        # Assert
        assert response.status_code == 502
        assert response.json()["error"] == "Failed to list files"

    @patch("maf_onedrive_integration.app.OneDriveClient")
    @patch("maf_onedrive_integration.app.AuthorizationCodeCredential")
    async def test_returns_files_for_site_id(
        self, mock_cred_cls: MagicMock, mock_client_cls: MagicMock
    ) -> None:
        # Arrange
        mock_cred_cls.return_value = _login_mocks()

        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_user_display_name.return_value = "User"
        mock_client.get_site_default_drive_id.return_value = "site-drive-99"
        mock_client.list_items.return_value = [
            DriveItemInfo(id="item-s1", name="Shared.docx", size=4096),
        ]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/auth/callback?code=test-code")

            # Act
            response = await client.get("/api/files?site_id=site-abc-123")

        # Assert
        assert response.status_code == 200
        mock_client.get_site_default_drive_id.assert_called_once_with("site-abc-123")
        mock_client.list_items.assert_called_once_with("site-drive-99")
        assert response.json()[0]["name"] == "Shared.docx"

    @patch("maf_onedrive_integration.app.OneDriveClient")
    @patch("maf_onedrive_integration.app.AuthorizationCodeCredential")
    async def test_returns_files_for_explicit_drive_id(
        self, mock_cred_cls: MagicMock, mock_client_cls: MagicMock
    ) -> None:
        # Arrange
        mock_cred_cls.return_value = _login_mocks()

        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_user_display_name.return_value = "User"
        mock_client.list_items.return_value = []

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/auth/callback?code=test-code")

            # Act
            response = await client.get("/api/files?drive_id=explicit-drive-id")

        # Assert
        assert response.status_code == 200
        mock_client.get_my_drive_id.assert_not_called()
        mock_client.get_site_default_drive_id.assert_not_called()
        mock_client.list_items.assert_called_once_with("explicit-drive-id")


class TestApiSites:
    async def test_unauthenticated_returns_401(self) -> None:
        # Arrange
        transport = ASGITransport(app=app)

        # Act
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/sites")

        # Assert
        assert response.status_code == 401

    @patch("maf_onedrive_integration.app.OneDriveClient")
    @patch("maf_onedrive_integration.app.AuthorizationCodeCredential")
    async def test_returns_site_list(
        self, mock_cred_cls: MagicMock, mock_client_cls: MagicMock
    ) -> None:
        # Arrange
        mock_cred_cls.return_value = _login_mocks()

        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_user_display_name.return_value = "User"
        mock_client.list_followed_sites.return_value = [
            SiteInfo(
                id="site-1",
                name="team-site",
                display_name="Team Site",
                web_url="https://contoso.sharepoint.com/sites/team",
            ),
            SiteInfo(
                id="site-2",
                name="project-x",
                display_name="Project X",
                web_url="https://contoso.sharepoint.com/sites/project-x",
            ),
        ]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/auth/callback?code=test-code")

            # Act
            response = await client.get("/api/sites")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["display_name"] == "Team Site"
        assert data[1]["id"] == "site-2"

    @patch("maf_onedrive_integration.app.OneDriveClient")
    @patch("maf_onedrive_integration.app.AuthorizationCodeCredential")
    async def test_graph_api_error_returns_502(
        self, mock_cred_cls: MagicMock, mock_client_cls: MagicMock
    ) -> None:
        # Arrange
        mock_cred_cls.return_value = _login_mocks()

        call_count = 0
        mock_client = AsyncMock()
        mock_client.get_user_display_name.return_value = "User"

        def make_client(**kwargs: object) -> AsyncMock:
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                mock_client.list_followed_sites.side_effect = RuntimeError(
                    "Sites API error"
                )
            return mock_client

        mock_client_cls.side_effect = make_client

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/auth/callback?code=test-code")

            # Act
            response = await client.get("/api/sites")

        # Assert
        assert response.status_code == 502
        assert response.json()["error"] == "Failed to list sites"


class TestApiSummarize:
    async def test_unauthenticated_returns_401(self) -> None:
        # Arrange
        transport = ASGITransport(app=app)

        # Act
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/summarize?item_id=x")

        # Assert
        assert response.status_code == 401

    @patch("maf_onedrive_integration.app.OneDriveClient")
    @patch("maf_onedrive_integration.app.AuthorizationCodeCredential")
    async def test_missing_item_id_returns_400(
        self, mock_cred_cls: MagicMock, mock_client_cls: MagicMock
    ) -> None:
        # Arrange
        mock_cred_cls.return_value = _login_mocks()
        mock_client = AsyncMock()
        mock_client.get_user_display_name.return_value = "User"
        mock_client_cls.return_value = mock_client

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/auth/callback?code=c")

            # Act
            response = await client.post("/api/summarize")

        # Assert
        assert response.status_code == 400
        assert response.json()["error"] == "item_id is required"

    @patch("maf_onedrive_integration.app.summarize_file_content")
    @patch("maf_onedrive_integration.app.OneDriveClient")
    @patch("maf_onedrive_integration.app.AuthorizationCodeCredential")
    async def test_successful_summary(
        self,
        mock_cred_cls: MagicMock,
        mock_client_cls: MagicMock,
        mock_summarize: AsyncMock,
    ) -> None:
        # Arrange
        mock_cred_cls.return_value = _login_mocks()

        mock_client = AsyncMock()
        mock_client._client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_user_display_name.return_value = "User"
        mock_client.get_my_drive_id.return_value = "drive-1"
        mock_client.get_item.return_value = DriveItemInfo(
            id="file-1", name="report.pdf", size=1024
        )
        (
            mock_client._client.drives.by_drive_id.return_value.items.by_drive_item_id.return_value.content.get
        ) = AsyncMock(return_value=b"PDF-BYTES")

        mock_summarize.return_value = SummaryResult(
            success=True, summary="This is a summary."
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/auth/callback?code=c")

            # Act
            response = await client.post("/api/summarize?item_id=file-1")

        # Assert
        assert response.status_code == 200
        assert response.json()["summary"] == "This is a summary."
        mock_summarize.assert_called_once_with(b"PDF-BYTES", "report.pdf")

    @patch("maf_onedrive_integration.app.summarize_file_content")
    @patch("maf_onedrive_integration.app.OneDriveClient")
    @patch("maf_onedrive_integration.app.AuthorizationCodeCredential")
    async def test_summary_agent_error_returns_422(
        self,
        mock_cred_cls: MagicMock,
        mock_client_cls: MagicMock,
        mock_summarize: AsyncMock,
    ) -> None:
        # Arrange
        mock_cred_cls.return_value = _login_mocks()

        mock_client = AsyncMock()
        mock_client._client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_user_display_name.return_value = "User"
        mock_client.get_my_drive_id.return_value = "drive-1"
        mock_client.get_item.return_value = DriveItemInfo(
            id="file-1", name="image.bmp", size=512
        )
        (
            mock_client._client.drives.by_drive_id.return_value.items.by_drive_item_id.return_value.content.get
        ) = AsyncMock(return_value=b"BMP-BYTES")

        mock_summarize.return_value = SummaryResult(
            success=False, error="Could not convert 'image.bmp' to Markdown."
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/auth/callback?code=c")

            # Act
            response = await client.post("/api/summarize?item_id=file-1")

        # Assert
        assert response.status_code == 422
        assert "Could not convert" in response.json()["error"]

    @patch("maf_onedrive_integration.app.OneDriveClient")
    @patch("maf_onedrive_integration.app.AuthorizationCodeCredential")
    async def test_download_failure_returns_502(
        self, mock_cred_cls: MagicMock, mock_client_cls: MagicMock
    ) -> None:
        # Arrange
        mock_cred_cls.return_value = _login_mocks()

        call_count = 0
        mock_client = AsyncMock()
        mock_client.get_user_display_name.return_value = "User"

        def make_client(**kwargs: object) -> AsyncMock:
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                mock_client.get_my_drive_id.side_effect = RuntimeError("Graph API down")
            return mock_client

        mock_client_cls.side_effect = make_client

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/auth/callback?code=c")

            # Act
            response = await client.post("/api/summarize?item_id=file-1")

        # Assert
        assert response.status_code == 502
        assert response.json()["error"] == "Failed to download the file"

    @patch("maf_onedrive_integration.app.OneDriveClient")
    @patch("maf_onedrive_integration.app.AuthorizationCodeCredential")
    async def test_no_content_returns_502(
        self, mock_cred_cls: MagicMock, mock_client_cls: MagicMock
    ) -> None:
        # Arrange
        mock_cred_cls.return_value = _login_mocks()

        mock_client = AsyncMock()
        mock_client._client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_user_display_name.return_value = "User"
        mock_client.get_my_drive_id.return_value = "drive-1"
        mock_client.get_item.return_value = DriveItemInfo(
            id="file-1", name="empty.pdf", size=0
        )
        (
            mock_client._client.drives.by_drive_id.return_value.items.by_drive_item_id.return_value.content.get
        ) = AsyncMock(return_value=None)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/auth/callback?code=c")

            # Act
            response = await client.post("/api/summarize?item_id=file-1")

        # Assert
        assert response.status_code == 502
        assert "no downloadable content" in response.json()["error"]

    @patch("maf_onedrive_integration.app.summarize_file_content")
    @patch("maf_onedrive_integration.app.OneDriveClient")
    @patch("maf_onedrive_integration.app.AuthorizationCodeCredential")
    async def test_uses_site_id_to_resolve_drive(
        self,
        mock_cred_cls: MagicMock,
        mock_client_cls: MagicMock,
        mock_summarize: AsyncMock,
    ) -> None:
        # Arrange
        mock_cred_cls.return_value = _login_mocks()

        mock_client = AsyncMock()
        mock_client._client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_user_display_name.return_value = "User"
        mock_client.get_site_default_drive_id.return_value = "site-drive-1"
        mock_client.get_item.return_value = DriveItemInfo(
            id="file-s1", name="notes.txt", size=100
        )
        (
            mock_client._client.drives.by_drive_id.return_value.items.by_drive_item_id.return_value.content.get
        ) = AsyncMock(return_value=b"TXT-BYTES")

        mock_summarize.return_value = SummaryResult(
            success=True, summary="Notes summary."
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/auth/callback?code=c")

            # Act
            response = await client.post(
                "/api/summarize?item_id=file-s1&site_id=site-abc"
            )

        # Assert
        assert response.status_code == 200
        mock_client.get_site_default_drive_id.assert_called_once_with("site-abc")
