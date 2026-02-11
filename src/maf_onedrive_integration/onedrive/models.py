"""Data models for OneDrive items."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True)
class DriveItemInfo:
    """Represents metadata about a file or folder in OneDrive."""

    id: str
    name: str
    size: int | None = None
    mime_type: str | None = None
    is_folder: bool = False
    created_at: datetime | None = None
    modified_at: datetime | None = None
    web_url: str | None = None
    download_url: str | None = None

    @property
    def is_file(self) -> bool:
        """Return True if this item is a file."""
        return not self.is_folder


@dataclass(frozen=True)
class FolderInfo:
    """Represents metadata about a folder including its children."""

    id: str
    name: str
    children: list[DriveItemInfo]
    web_url: str | None = None


@dataclass(frozen=True)
class SiteInfo:
    """Represents metadata about a SharePoint site."""

    id: str
    name: str
    display_name: str
    web_url: str | None = None
