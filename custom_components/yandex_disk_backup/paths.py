"""Pure path helpers for Yandex Disk backup storage."""

from collections.abc import Mapping
from typing import Any

from homeassistant.util import slugify

from .const import (
    APP_FOLDER_ROOT,
    CONF_BACKUP_FOLDER,
    CONF_INSTANCE_FOLDER,
    CONF_STORAGE_MODE,
    DEFAULT_BACKUP_FOLDER,
    STORAGE_MODE_APP_FOLDER,
)

_FORBIDDEN_CHARS = set("\\:%?#")


class InvalidPathError(ValueError):
    """Raised when a folder or file name is not acceptable."""


def validate_instance_folder(value: str) -> str:
    """Validate the instance folder name; return it unchanged."""
    if not value:
        raise InvalidPathError("Folder must not be empty")
    if value != value.strip():
        raise InvalidPathError("Folder must not have surrounding whitespace")
    if value.startswith("/") or value.endswith("/"):
        raise InvalidPathError("Folder must not start or end with '/'")
    if any(ch in _FORBIDDEN_CHARS for ch in value):
        raise InvalidPathError("Folder contains forbidden characters")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise InvalidPathError("Folder contains control characters")
    for segment in value.split("/"):
        if segment in ("", ".", ".."):
            raise InvalidPathError("Folder contains an invalid path segment")
    return value


def make_unique_id(uid: str, storage_mode: str, folder: str) -> str:
    """Return the config entry unique_id for an account, mode and folder.

    The folder is slugified because HA builds the backup agent_id from the
    unique_id and the frontend cannot open agent pages whose ids contain
    spaces or non-ASCII characters.
    """
    return f"{uid}:{storage_mode}:{slugify(folder)}"


def resolve_base_path(config: Mapping[str, Any]) -> str:
    """Return the base folder path for the given config entry data."""
    if config.get(CONF_STORAGE_MODE) == STORAGE_MODE_APP_FOLDER:
        folder = validate_instance_folder(str(config.get(CONF_INSTANCE_FOLDER, "")))
        return f"{APP_FOLDER_ROOT}{folder}"
    return str(config.get(CONF_BACKUP_FOLDER) or DEFAULT_BACKUP_FOLDER)


def join_filename(base: str, filename: str) -> str:
    """Join a base folder and a plain file name."""
    if not filename or filename in (".", "..") or "/" in filename or "\\" in filename:
        raise InvalidPathError("Invalid file name")
    return f"{base.rstrip('/')}/{filename}"


def folder_chain(base: str) -> list[str]:
    """Return every folder to create for base, root excluded."""
    prefix = ""
    rest = base
    head, sep, tail = base.partition(":/")
    if sep and "/" not in head:
        prefix = f"{head}:/"
        rest = tail
    elif base.startswith("/"):
        prefix = "/"
        rest = base[1:]
    chain: list[str] = []
    current = prefix
    for segment in (s for s in rest.split("/") if s):
        current = (
            f"{current.rstrip('/')}/{segment}"
            if current != prefix
            else f"{prefix}{segment}"
        )
        chain.append(current)
    return chain
