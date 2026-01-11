"""The Yandex Disk backup integration."""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DATA_BACKUP_AGENT_LISTENERS, DOMAIN
from .backup import YandexDiskBackupAgent

type YandexDiskConfigEntry = ConfigEntry[dict[str, Any]]

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[str] = []


async def async_setup(  # pylint: disable=unused-argument
    hass: HomeAssistant, config: ConfigType
) -> bool:
    """Set up the Yandex Disk backup component.

    Args:
        hass: Home Assistant instance
        config: Component configuration

    Returns:
        True if setup succeeded
    """
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: YandexDiskConfigEntry) -> bool:
    """Set up Yandex Disk backup from a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry

    Returns:
        True if setup succeeded
    """
    hass.data.setdefault(DOMAIN, {})

    # Store entry data for backup agent to use
    entry.runtime_data = dict(entry.data)

    def async_notify_backup_listeners() -> None:
        """Notify all registered backup listeners."""
        for listener in hass.data.get(DATA_BACKUP_AGENT_LISTENERS, []):
            listener()

    # Register listener notification on entry state change
    entry.async_on_unload(entry.async_on_state_change(async_notify_backup_listeners))

    # Forward entry setup to backup platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Notify listeners that agents have changed
    async_notify_backup_listeners()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: YandexDiskConfigEntry) -> bool:
    """Unload a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry to unload

    Returns:
        True if unload succeeded
    """
    # Forward entry unload to backup platform
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Notify listeners that agents have changed
    if unload_ok:
        for listener in hass.data.get(DATA_BACKUP_AGENT_LISTENERS, []):
            listener()

    return unload_ok
