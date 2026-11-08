"""The Yandex Disk backup integration."""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import (
    APP_CLIENT_ID,
    AUTH_METHOD_DEVICE,
    AUTH_METHOD_MANUAL,
    AUTH_METHOD_OAUTH,
    CONF_AUTH_METHOD,
    CONF_BACKUP_FOLDER,
    CONF_INSTANCE_FOLDER,
    CONF_STORAGE_MODE,
    DATA_BACKUP_AGENT_LISTENERS,
    DEFAULT_BACKUP_FOLDER,
    DOMAIN,
    RUNTIME_TOKEN_MANAGER,
    STORAGE_MODE_APP_FOLDER,
)
from .backup import YandexDiskBackupAgent
from .oauth import OAuthConnectionError, YandexOAuthClient
from .paths import make_unique_id
from .token_manager import TokenManager, TokenNetworkError, TokenRefreshError

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


@callback
def _async_migrate_unique_id(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Rewrite unique_id to the slugified form used by make_unique_id.

    Entries created before the slug change keep the raw folder name in
    unique_id, which produces agent ids the frontend cannot open. Legacy
    entries without a storage_mode are left untouched.
    """
    mode = entry.data.get(CONF_STORAGE_MODE)
    if mode is None or not entry.unique_id:
        return
    if entry.data.get(CONF_AUTH_METHOD) == AUTH_METHOD_MANUAL:
        # Token entries keep the token-prefix unique_id; nothing to rewrite.
        return
    if mode == STORAGE_MODE_APP_FOLDER:
        folder = entry.data.get(CONF_INSTANCE_FOLDER, "")
    else:
        folder = entry.data.get(CONF_BACKUP_FOLDER, DEFAULT_BACKUP_FOLDER)
    uid = entry.unique_id.split(":", 1)[0]
    new_unique_id = make_unique_id(uid, mode, folder)
    if new_unique_id == entry.unique_id:
        return
    if any(
        other.entry_id != entry.entry_id and other.unique_id == new_unique_id
        for other in hass.config_entries.async_entries(DOMAIN)
    ):
        _LOGGER.warning(
            "Cannot migrate unique_id of %s: %s is already used by another entry",
            entry.title,
            new_unique_id,
        )
        return
    _LOGGER.info("Migrating unique_id %s -> %s", entry.unique_id, new_unique_id)
    hass.config_entries.async_update_entry(entry, unique_id=new_unique_id)


async def async_setup_entry(hass: HomeAssistant, entry: YandexDiskConfigEntry) -> bool:
    """Set up Yandex Disk backup from a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry

    Returns:
        True if setup succeeded
    """
    hass.data.setdefault(DOMAIN, {})
    _async_migrate_unique_id(hass, entry)

    auth_method = entry.data.get(CONF_AUTH_METHOD)
    if auth_method == AUTH_METHOD_DEVICE:
        # Unreleased device-flow entries refreshed with a client secret. The
        # secret is no longer used, so the user signs in again.
        raise ConfigEntryAuthFailed("Yandex Disk sign-in must be repeated")
    if auth_method == AUTH_METHOD_OAUTH:
        # Built-in public app: refresh without a client secret.
        oauth = YandexOAuthClient(async_get_clientsession(hass), APP_CLIENT_ID)
        manager = TokenManager(hass, entry, oauth)
        try:
            await manager.async_get_access_token()
        except TokenNetworkError as err:
            raise ConfigEntryNotReady("Cannot refresh Yandex Disk token") from err
        except TokenRefreshError as err:
            raise ConfigEntryAuthFailed("Yandex Disk authorization expired") from err
        except OAuthConnectionError as err:
            raise ConfigEntryNotReady("Cannot reach Yandex OAuth") from err
        entry.runtime_data = {**entry.data, RUNTIME_TOKEN_MANAGER: manager}
    else:
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
