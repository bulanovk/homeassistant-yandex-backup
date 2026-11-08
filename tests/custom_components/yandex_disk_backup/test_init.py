"""Tests for Yandex Disk backup integration setup."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.yandex_disk_backup import (
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.yandex_disk_backup.backup import (
    async_get_backup_agents,
    async_register_backup_agents_listener,
)
from custom_components.yandex_disk_backup.const import (
    CONF_BACKUP_FOLDER,
    CONF_TOKEN,
    DATA_BACKUP_AGENT_LISTENERS,
    DOMAIN,
)


@pytest.mark.asyncio
async def test_async_setup(hass: HomeAssistant):
    """Test component setup."""
    result = await async_setup(hass, {})

    assert result is True
    assert DOMAIN in hass.data


@pytest.mark.asyncio
async def test_async_setup_entry(hass: HomeAssistant):
    """Test config entry setup."""
    # Create a mock config entry
    config_entry = Mock(spec=ConfigEntry)
    config_entry.entry_id = "test_entry_id"
    config_entry.runtime_data = {}
    config_entry.data = {
        CONF_TOKEN: "test_token",
        CONF_BACKUP_FOLDER: "/Home Assistant Backups",
    }
    config_entry.unique_id = "test_unique_id"

    # Mock async_on_unload and async_on_state_change
    config_entry.async_on_unload = Mock()
    config_entry.async_on_state_change = Mock(return_value=Mock())

    # Mock async_forward_entry_setups
    with patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        new=AsyncMock(return_value=True),
    ):
        result = await async_setup_entry(hass, config_entry)

        assert result is True
        assert DOMAIN in hass.data
        config_entry.async_on_unload.assert_called_once()
        config_entry.async_on_state_change.assert_called_once()
        hass.config_entries.async_forward_entry_setups.assert_called_once()


@pytest.mark.asyncio
async def test_async_setup_entry_stores_runtime_data(hass: HomeAssistant):
    """Test that config entry setup stores runtime data."""
    config_entry = Mock(spec=ConfigEntry)
    config_entry.entry_id = "test_entry_id"
    config_entry.data = {
        CONF_TOKEN: "test_token",
        CONF_BACKUP_FOLDER: "/Custom Folder",
    }
    config_entry.unique_id = "test_unique_id"
    config_entry.async_on_unload = Mock()
    config_entry.async_on_state_change = Mock(return_value=Mock())

    with patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        new=AsyncMock(return_value=True),
    ):
        await async_setup_entry(hass, config_entry)

        assert config_entry.runtime_data == config_entry.data


@pytest.mark.asyncio
async def test_async_unload_entry(hass: HomeAssistant):
    """Test config entry unload."""
    config_entry = Mock(spec=ConfigEntry)
    config_entry.entry_id = "test_entry_id"
    config_entry.data = {
        CONF_TOKEN: "test_token",
        CONF_BACKUP_FOLDER: "/Home Assistant Backups",
    }

    # Mock async_unload_platforms to return True
    with patch.object(
        hass.config_entries, "async_unload_platforms", new=AsyncMock(return_value=True)
    ):
        result = await async_unload_entry(hass, config_entry)

        assert result is True
        hass.config_entries.async_unload_platforms.assert_called_once()


@pytest.mark.asyncio
async def test_async_unload_entry_failure(hass: HomeAssistant):
    """Test config entry unload failure."""
    config_entry = Mock(spec=ConfigEntry)
    config_entry.entry_id = "test_entry_id"
    config_entry.data = {
        CONF_TOKEN: "test_token",
        CONF_BACKUP_FOLDER: "/Home Assistant Backups",
    }

    # Mock async_unload_platforms to return False
    with patch.object(
        hass.config_entries, "async_unload_platforms", new=AsyncMock(return_value=False)
    ):
        result = await async_unload_entry(hass, config_entry)

        assert result is False


def test_async_register_backup_agents_listener(hass: HomeAssistant):
    """Test registering a backup agents listener."""
    listener = Mock()

    unsubscribe = async_register_backup_agents_listener(hass, listener=listener)

    assert DATA_BACKUP_AGENT_LISTENERS in hass.data
    assert listener in hass.data[DATA_BACKUP_AGENT_LISTENERS]

    # Test unsubscribe
    unsubscribe()
    # After unsubscribe, listener should be removed from the list
    if DATA_BACKUP_AGENT_LISTENERS in hass.data:
        assert listener not in hass.data[DATA_BACKUP_AGENT_LISTENERS]


@pytest.mark.asyncio
async def test_async_get_backup_agents(hass: HomeAssistant):
    """Test getting backup agents."""
    # Create mock config entries
    config_entry1 = Mock(spec=ConfigEntry)
    config_entry1.entry_id = "entry1"
    config_entry1.runtime_data = {CONF_TOKEN: "token1"}
    config_entry1.unique_id = "unique1"

    config_entry2 = Mock(spec=ConfigEntry)
    config_entry2.entry_id = "entry2"
    config_entry2.runtime_data = {CONF_TOKEN: "token2"}
    config_entry2.unique_id = "unique2"

    # Mock async_loaded_entries
    with patch.object(
        hass.config_entries,
        "async_loaded_entries",
        return_value=[config_entry1, config_entry2],
    ):
        agents = await async_get_backup_agents(hass)

        assert len(agents) == 2
        # agent_id is prefixed with DOMAIN, uses translated name (default: "Yandex Disk")
        assert agents[0].agent_id.startswith(f"{DOMAIN}.")
        assert agents[1].agent_id.startswith(f"{DOMAIN}.")
        # Verify unique_id is stored correctly in agent
        assert agents[0].unique_id == "unique1"
        assert agents[1].unique_id == "unique2"


@pytest.mark.asyncio
async def test_async_get_backup_agents_empty(hass: HomeAssistant):
    """Test getting backup agents when none are loaded."""
    with patch.object(hass.config_entries, "async_loaded_entries", return_value=[]):
        agents = await async_get_backup_agents(hass)

        assert len(agents) == 0


@pytest.mark.asyncio
async def test_async_setup_entry_forward_entry_fails(hass: HomeAssistant):
    """Test config entry setup when forward entry setup fails."""
    from homeassistant.config_entries import ConfigEntry

    config_entry = Mock(spec=ConfigEntry)
    config_entry.entry_id = "test_entry_id"
    config_entry.data = {
        CONF_TOKEN: "test_token",
        CONF_BACKUP_FOLDER: "/Home Assistant Backups",
    }
    config_entry.unique_id = "test_unique_id"
    config_entry.async_on_unload = Mock()
    config_entry.async_on_state_change = Mock(return_value=Mock())

    # Mock async_forward_entry_setups to raise an exception
    with patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        new=AsyncMock(side_effect=Exception("Setup failed")),
    ):
        with pytest.raises(Exception, match="Setup failed"):
            await async_setup_entry(hass, config_entry)


@pytest.mark.asyncio
async def test_async_unload_entry_unload_fails(hass: HomeAssistant):
    """Test config entry unload when async_unload_platforms fails."""
    from homeassistant.config_entries import ConfigEntry

    config_entry = Mock(spec=ConfigEntry)
    config_entry.entry_id = "test_entry_id"
    config_entry.data = {
        CONF_TOKEN: "test_token",
        CONF_BACKUP_FOLDER: "/Home Assistant Backups",
    }

    # Mock async_unload_platforms to raise an exception
    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        new=AsyncMock(side_effect=Exception("Unload failed")),
    ):
        with pytest.raises(Exception, match="Unload failed"):
            await async_unload_entry(hass, config_entry)


def _oauth_entry(expires_in_days):
    import time

    from custom_components.yandex_disk_backup.const import (
        AUTH_METHOD_OAUTH,
        CONF_AUTH_METHOD,
        CONF_EXPIRES_AT,
        CONF_REFRESH_TOKEN,
    )

    entry = Mock(spec=ConfigEntry)
    entry.entry_id = "oauth_entry"
    entry.unique_id = "uid:app_folder:home"
    entry.runtime_data = {}
    entry.data = {
        CONF_TOKEN: "A",
        CONF_REFRESH_TOKEN: "R",
        CONF_EXPIRES_AT: time.time() + expires_in_days * 24 * 3600,
        CONF_AUTH_METHOD: AUTH_METHOD_OAUTH,
        "storage_mode": "app_folder",
        "instance_folder": "home",
    }
    entry.async_on_unload = Mock()
    entry.async_on_state_change = Mock(return_value=Mock())
    entry.async_start_reauth = Mock()
    return entry


@pytest.mark.asyncio
async def test_oauth_entry_refresh_failure_is_auth_failed(hass: HomeAssistant):
    from homeassistant.exceptions import ConfigEntryAuthFailed

    from custom_components.yandex_disk_backup.token_manager import TokenRefreshError

    entry = _oauth_entry(expires_in_days=1)
    with patch("custom_components.yandex_disk_backup.async_get_clientsession"), patch(
        "custom_components.yandex_disk_backup.YandexOAuthClient"
    ), patch(
        "custom_components.yandex_disk_backup.TokenManager.async_get_access_token",
        new=AsyncMock(side_effect=TokenRefreshError("invalid_grant")),
    ):
        with pytest.raises(ConfigEntryAuthFailed):
            await async_setup_entry(hass, entry)


@pytest.mark.asyncio
async def test_oauth_entry_network_error_is_not_ready(hass: HomeAssistant):
    from homeassistant.exceptions import ConfigEntryNotReady

    from custom_components.yandex_disk_backup.token_manager import TokenNetworkError

    entry = _oauth_entry(expires_in_days=-1)
    with patch("custom_components.yandex_disk_backup.async_get_clientsession"), patch(
        "custom_components.yandex_disk_backup.YandexOAuthClient"
    ), patch(
        "custom_components.yandex_disk_backup.TokenManager.async_get_access_token",
        new=AsyncMock(side_effect=TokenNetworkError("network_error")),
    ):
        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, entry)


@pytest.mark.asyncio
async def test_oauth_entry_success_stores_manager(hass: HomeAssistant):
    from custom_components.yandex_disk_backup.const import RUNTIME_TOKEN_MANAGER
    from custom_components.yandex_disk_backup.token_manager import TokenManager

    entry = _oauth_entry(expires_in_days=60)
    with patch("custom_components.yandex_disk_backup.async_get_clientsession"), patch(
        "custom_components.yandex_disk_backup.YandexOAuthClient"
    ), patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        new=AsyncMock(return_value=True),
    ):
        assert await async_setup_entry(hass, entry) is True
    assert isinstance(entry.runtime_data[RUNTIME_TOKEN_MANAGER], TokenManager)


@pytest.mark.asyncio
async def test_device_entry_requires_new_sign_in(hass: HomeAssistant):
    from homeassistant.exceptions import ConfigEntryAuthFailed

    from custom_components.yandex_disk_backup.const import (
        AUTH_METHOD_DEVICE,
        CONF_AUTH_METHOD,
    )

    entry = _oauth_entry(expires_in_days=60)
    entry.data = {**entry.data, CONF_AUTH_METHOD: AUTH_METHOD_DEVICE}
    with patch("custom_components.yandex_disk_backup.async_get_clientsession"), patch(
        "custom_components.yandex_disk_backup.YandexOAuthClient"
    ) as cls:
        with pytest.raises(ConfigEntryAuthFailed):
            await async_setup_entry(hass, entry)
    cls.assert_not_called()


@pytest.mark.asyncio
async def test_oauth_entry_uses_builtin_client(hass: HomeAssistant):
    from custom_components.yandex_disk_backup.const import APP_CLIENT_ID

    entry = _oauth_entry(expires_in_days=60)
    with patch("custom_components.yandex_disk_backup.async_get_clientsession"), patch(
        "custom_components.yandex_disk_backup.YandexOAuthClient"
    ) as cls, patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        new=AsyncMock(return_value=True),
    ):
        assert await async_setup_entry(hass, entry) is True
    assert cls.call_args.args[1] == APP_CLIENT_ID


def _app_entry(unique_id, folder, entry_id="e1"):
    entry = Mock(spec=ConfigEntry)
    entry.entry_id = entry_id
    entry.title = "Yandex Disk"
    entry.unique_id = unique_id
    entry.data = {"storage_mode": "app_folder", "instance_folder": folder}
    return entry


def test_migrate_unique_id_rewrites_raw_folder(hass: HomeAssistant):
    """Old unique_ids with spaces are rewritten to the slug form."""
    from custom_components.yandex_disk_backup import _async_migrate_unique_id

    entry = _app_entry("40359235:app_folder:Home Assistant", "Home Assistant")
    hass.config_entries.async_entries = Mock(return_value=[entry])
    hass.config_entries.async_update_entry = Mock()

    _async_migrate_unique_id(hass, entry)

    hass.config_entries.async_update_entry.assert_called_once_with(
        entry, unique_id="40359235:app_folder:home_assistant"
    )


def test_migrate_unique_id_skips_conflict(hass: HomeAssistant):
    """A migration that would collide with another entry is skipped."""
    from custom_components.yandex_disk_backup import _async_migrate_unique_id

    entry = _app_entry("40359235:app_folder:Home Assistant", "Home Assistant")
    other = _app_entry("40359235:app_folder:home_assistant", "home_assistant", "e2")
    hass.config_entries.async_entries = Mock(return_value=[entry, other])
    hass.config_entries.async_update_entry = Mock()

    _async_migrate_unique_id(hass, entry)

    hass.config_entries.async_update_entry.assert_not_called()


def test_migrate_unique_id_leaves_legacy_entries(hass: HomeAssistant):
    """Entries without storage_mode keep their unique_id."""
    from custom_components.yandex_disk_backup import _async_migrate_unique_id

    entry = Mock(spec=ConfigEntry)
    entry.entry_id = "legacy"
    entry.unique_id = "abcd1234"
    entry.data = {CONF_TOKEN: "t", CONF_BACKUP_FOLDER: "/Home Assistant Backups"}
    hass.config_entries.async_update_entry = Mock()

    _async_migrate_unique_id(hass, entry)

    hass.config_entries.async_update_entry.assert_not_called()


def test_migrate_unique_id_skips_manual_token_entries(hass: HomeAssistant):
    """Token entries keep their token-prefix unique_id even with a storage_mode."""
    from custom_components.yandex_disk_backup import _async_migrate_unique_id

    entry = _app_entry("abcd1234", "home")
    entry.data = {**entry.data, "auth_method": "manual"}
    hass.config_entries.async_update_entry = Mock()

    _async_migrate_unique_id(hass, entry)

    hass.config_entries.async_update_entry.assert_not_called()
