"""FastAPI web application for browsing OneDrive files."""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from azure.identity import AuthorizationCodeCredential
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from maf_onedrive_integration.onedrive.client import OneDriveClient

if TYPE_CHECKING:
    from starlette.responses import Response

load_dotenv()

logger = logging.getLogger(__name__)

app = FastAPI(title="MAF OneDrive Browser")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", os.urandom(32).hex()),
)

STATIC_DIR = Path(__file__).parent / "static"

SCOPES = ["User.Read", "Files.Read.All", "Sites.Read.All"]

# Azure AD configuration — read once from the environment.
_CLIENT_ID = os.environ.get("APPLICATION_ID", "")
_CLIENT_SECRET = os.environ.get("APPLICATION_SECRET", "")
_REDIRECT_URI = os.environ.get("REDIRECT_URI", "http://localhost:8000/auth/callback")
_TENANT_ID = os.environ.get("TENANT_ID", "common")
_AUTHORITY = f"https://login.microsoftonline.com/{_TENANT_ID}"

# Server-side credential store: maps session ID → credential.
# The ``AuthorizationCodeCredential`` handles token caching and refresh
# automatically, so we keep a live reference per logged-in user.
_credentials: dict[str, AuthorizationCodeCredential] = {}


def _get_credential(request: Request) -> AuthorizationCodeCredential | None:
    """Look up the user's credential from the server-side store."""
    sid = request.session.get("sid")
    if not sid:
        return None
    return _credentials.get(sid)


@app.get("/")
async def index() -> FileResponse:
    """Serve the single-page frontend."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/login")
async def login() -> RedirectResponse:
    """Redirect the user to the Azure AD login page."""
    params = {
        "client_id": _CLIENT_ID,
        "response_type": "code",
        "redirect_uri": _REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "response_mode": "query",
    }
    auth_url = f"{_AUTHORITY}/oauth2/v2.0/authorize?{urlencode(params)}"
    return RedirectResponse(auth_url)


@app.get("/auth/callback")
async def auth_callback(request: Request) -> Response:
    """Handle the OAuth2 authorization-code callback from Azure AD."""
    code = request.query_params.get("code")
    if not code:
        return RedirectResponse("/")

    credential = AuthorizationCodeCredential(
        tenant_id=_TENANT_ID,
        client_id=_CLIENT_ID,
        authorization_code=code,
        redirect_uri=_REDIRECT_URI,
        client_secret=_CLIENT_SECRET,
    )

    # Validate the code and fetch the user name in one shot.
    # The Graph SDK will call credential.get_token() internally, which
    # redeems the authorization code and caches access + refresh tokens.
    client = OneDriveClient(credential=credential)
    try:
        user_name = await client.get_user_display_name()
    except Exception:
        logger.exception("Failed to authenticate with authorization code")
        return JSONResponse(
            {
                "error": "authentication_failed",
                "description": "Failed to redeem authorization code.",
            },
            status_code=400,
        )

    # Store credential server-side; only keep session ID in cookie.
    sid = uuid.uuid4().hex
    _credentials[sid] = credential
    request.session["sid"] = sid
    request.session["user_name"] = user_name
    return RedirectResponse("/")


@app.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    """Clear the session and remove the server-side credential."""
    sid = request.session.get("sid")
    if sid:
        _credentials.pop(sid, None)
    request.session.clear()
    return RedirectResponse("/")


@app.get("/api/me")
async def me(request: Request) -> JSONResponse:
    """Return the current user's display name, or *401* if not logged in."""
    credential = _get_credential(request)
    if not credential:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    return JSONResponse({"name": request.session.get("user_name", "User")})


@app.get("/api/sites")
async def list_sites(request: Request) -> JSONResponse:
    """Return the SharePoint sites the user follows."""
    credential = _get_credential(request)
    if not credential:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    client = OneDriveClient(credential=credential)

    try:
        sites = await client.list_followed_sites()
    except Exception:
        logger.exception("Failed to list followed sites")
        return JSONResponse({"error": "Failed to list sites"}, status_code=502)

    return JSONResponse(
        [
            {
                "id": site.id,
                "name": site.name,
                "display_name": site.display_name,
                "web_url": site.web_url,
            }
            for site in sites
        ]
    )


@app.get("/api/files")
async def list_files(
    request: Request, path: str = "", drive_id: str = "", site_id: str = ""
) -> JSONResponse:
    """List files and folders in the user's OneDrive or a SharePoint site.

    Query Parameters
    ----------------
    path:
        Optional subfolder path relative to the drive root.
    drive_id:
        Optional drive ID. When omitted the user's personal OneDrive is used.
    site_id:
        Optional SharePoint site ID. Resolves the site's default drive.
        Ignored when *drive_id* is provided.
    """
    credential = _get_credential(request)
    if not credential:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    client = OneDriveClient(credential=credential)

    try:
        if drive_id:
            resolved_drive_id = drive_id
        elif site_id:
            resolved_drive_id = await client.get_site_default_drive_id(site_id)
        else:
            resolved_drive_id = await client.get_my_drive_id()

        if path:
            items = await client.list_items_by_path(resolved_drive_id, path)
        else:
            items = await client.list_items(resolved_drive_id)
    except Exception:
        logger.exception("Failed to list OneDrive files")
        return JSONResponse({"error": "Failed to list files"}, status_code=502)

    return JSONResponse(
        [
            {
                "id": item.id,
                "name": item.name,
                "size": item.size,
                "is_folder": item.is_folder,
                "mime_type": item.mime_type,
                "modified_at": (
                    item.modified_at.isoformat() if item.modified_at else None
                ),
                "web_url": item.web_url,
            }
            for item in items
        ]
    )


def start() -> None:
    """Run the web application with uvicorn (used by the console script)."""
    import uvicorn

    uvicorn.run(
        "maf_onedrive_integration.app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    start()
