"""Diagnostics support for Yandex Disk backup integration."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, TO_REDACT


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

    diagnostics: dict[str, Any] = {
        "config": async_redact_data(entry.data, TO_REDACT),
        "backup_folder": entry.data.get("backup_folder"),
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
