"""Tests for Yandex Disk backup integration setup."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.yandex_disk_backup import async_setup, async_setup_entry, async_unload_entry
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
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock(return_value=True)
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
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock(return_value=True)
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
    with patch.object(
        hass.config_entries, "async_loaded_entries", return_value=[]
    ):
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
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock(side_effect=Exception("Setup failed"))
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
        hass.config_entries, "async_unload_platforms", new=AsyncMock(side_effect=Exception("Unload failed"))
    ):
        with pytest.raises(Exception, match="Unload failed"):
            await async_unload_entry(hass, config_entry)
