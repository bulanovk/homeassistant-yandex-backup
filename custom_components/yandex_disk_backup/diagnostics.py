"""Diagnostics support for Yandex Disk backup integration."""

from datetime import UTC, datetime
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    AUTH_METHOD_MANUAL,
    CONF_AUTH_METHOD,
    CONF_EXPIRES_AT,
    CONF_STORAGE_MODE,
    DOMAIN,
    STORAGE_MODE_DISK_FOLDER,
    TO_REDACT,
)
from .paths import InvalidPathError, resolve_base_path


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry

    Returns:
        Diagnostics data dictionary
    """
    # pylint: disable=protected-access
    agent = hass.data[DOMAIN].get(entry.entry_id)

    expires_at = entry.data.get(CONF_EXPIRES_AT)
    try:
        base_path: str | None = resolve_base_path(entry.data)
    except InvalidPathError:
        base_path = None

    diagnostics: dict[str, Any] = {
        "config": async_redact_data(entry.data, TO_REDACT),
        "backup_folder": entry.data.get("backup_folder"),
        "storage_mode": entry.data.get(CONF_STORAGE_MODE, STORAGE_MODE_DISK_FOLDER),
        "auth_method": entry.data.get(CONF_AUTH_METHOD, AUTH_METHOD_MANUAL),
        "base_path": base_path,
        "token_expires_at": (
            datetime.fromtimestamp(expires_at, UTC).isoformat()
            if isinstance(expires_at, (int, float))
            else None
        ),
    }

    if agent:
        try:
            # Get storage information
            disk_info = await agent._get_disk_info_cached()
            diagnostics["storage_info"] = {
                "total_space_gb": round(disk_info["total_space"] / (1024**3), 2),
                "used_space_gb": round(disk_info["used_space"] / (1024**3), 2),
                "free_space_gb": round(disk_info["free_space"] / (1024**3), 2),
                "used_percentage": (
                    round(
                        disk_info["used_space"] / disk_info["total_space"] * 100,
                        1,
                    )
                    if disk_info["total_space"] > 0
                    else 0
                ),
            }
        except Exception:  # pylint: disable=broad-exception-caught
            diagnostics["storage_info"] = {"error": "Failed to get storage info"}

        try:
            # Get backup count
            backups = await agent.async_list_backups()
            diagnostics["backup_count"] = len(backups)
            if backups:
                diagnostics["last_backup"] = backups[0].date
        except Exception:  # pylint: disable=broad-exception-caught
            diagnostics["backup_count"] = {"error": "Failed to list backups"}

    return diagnostics
