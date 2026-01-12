"""Tests for Yandex Disk backup diagnostics."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from yadisk.exceptions import YaDiskError

from custom_components.yandex_disk_backup.const import (
    CONF_BACKUP_FOLDER,
    CONF_TOKEN,
    DOMAIN,
)
from custom_components.yandex_disk_backup.diagnostics import (
    async_get_config_entry_diagnostics,
)


@pytest.mark.asyncio
async def test_diagnostics_without_agent(hass: HomeAssistant):
    """Test diagnostics when no agent exists."""
    config_entry = Mock(spec=ConfigEntry)
    config_entry.entry_id = "test_entry"
    config_entry.data = {
        CONF_TOKEN: "test_token_12345",
        CONF_BACKUP_FOLDER: "/Home Assistant Backups",
    }

    hass.data.setdefault(DOMAIN, {})

    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)

    assert "config" in diagnostics
    assert diagnostics["config"][CONF_TOKEN] == "**REDACTED**"
    assert diagnostics["backup_folder"] == "/Home Assistant Backups"
    assert "storage_info" not in diagnostics
    assert "backup_count" not in diagnostics


@pytest.mark.asyncio
async def test_diagnostics_with_storage_info(hass: HomeAssistant, backup_agent):
    """Test diagnostics with storage information."""
    config_entry = Mock(spec=ConfigEntry)
    config_entry.entry_id = "test_entry"
    config_entry.data = {
        CONF_TOKEN: "test_token_12345",
        CONF_BACKUP_FOLDER: "/Home Assistant Backups",
    }

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][config_entry.entry_id] = backup_agent

    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)

    assert "storage_info" in diagnostics
    assert "total_space_gb" in diagnostics["storage_info"]
    assert "used_space_gb" in diagnostics["storage_info"]
    assert "free_space_gb" in diagnostics["storage_info"]
    assert "used_percentage" in diagnostics["storage_info"]
    assert diagnostics["storage_info"]["total_space_gb"] == 10.0
    assert diagnostics["storage_info"]["used_space_gb"] == 2.0
    assert diagnostics["storage_info"]["free_space_gb"] == 8.0


@pytest.mark.asyncio
async def test_diagnostics_storage_info_error(hass: HomeAssistant, backup_agent):
    """Test diagnostics when storage info retrieval fails."""
    config_entry = Mock(spec=ConfigEntry)
    config_entry.entry_id = "test_entry"
    config_entry.data = {
        CONF_TOKEN: "test_token_12345",
        CONF_BACKUP_FOLDER: "/Home Assistant Backups",
    }

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][config_entry.entry_id] = backup_agent

    # Mock _get_disk_info_cached to raise an exception
    with patch.object(
        backup_agent, "_get_disk_info_cached", new=AsyncMock(side_effect=YaDiskError("API Error"))
    ):
        diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)

        assert "storage_info" in diagnostics
        assert diagnostics["storage_info"] == {"error": "Failed to get storage info"}


@pytest.mark.asyncio
async def test_diagnostics_with_backup_count(hass: HomeAssistant, backup_agent, mock_yadisk_client):
    """Test diagnostics with backup count information."""
    from datetime import datetime
    from unittest.mock import Mock

    config_entry = Mock(spec=ConfigEntry)
    config_entry.entry_id = "test_entry"
    config_entry.data = {
        CONF_TOKEN: "test_token_12345",
        CONF_BACKUP_FOLDER: "/Home Assistant Backups",
    }

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][config_entry.entry_id] = backup_agent

    from datetime import datetime
    from unittest.mock import Mock

    # Mock listdir to return a backup file
    item = Mock()
    item.name = "backup.tar"
    item.type = "file"
    item.created = datetime.now()

    async def listdir_impl(path):
        yield item

    mock_yadisk_client.listdir = listdir_impl

    # Mock get_meta
    async def mock_get_meta(path):
        meta = Mock()
        meta.name = "backup.tar"
        meta.size = 1024
        meta.created = datetime.now()
        return meta

    mock_yadisk_client.get_meta.side_effect = mock_get_meta

    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)

    assert "backup_count" in diagnostics
    assert diagnostics["backup_count"] == 1
    assert "last_backup" in diagnostics


@pytest.mark.asyncio
async def test_diagnostics_backup_count_error(hass: HomeAssistant, backup_agent):
    """Test diagnostics when backup listing fails."""
    config_entry = Mock(spec=ConfigEntry)
    config_entry.entry_id = "test_entry"
    config_entry.data = {
        CONF_TOKEN: "test_token_12345",
        CONF_BACKUP_FOLDER: "/Home Assistant Backups",
    }

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][config_entry.entry_id] = backup_agent

    # Mock async_list_backups to raise an exception
    with patch.object(
        backup_agent, "async_list_backups", new=AsyncMock(side_effect=YaDiskError("API Error"))
    ):
        diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)

        assert "backup_count" in diagnostics
        assert diagnostics["backup_count"] == {"error": "Failed to list backups"}


@pytest.mark.asyncio
async def test_diagnostics_token_redaction(hass: HomeAssistant, backup_agent):
    """Test that OAuth tokens are properly redacted."""
    config_entry = Mock(spec=ConfigEntry)
    config_entry.entry_id = "test_entry"
    config_entry.data = {
        CONF_TOKEN: "secret_oauth_token_abc123",
        CONF_BACKUP_FOLDER: "/Home Assistant Backups",
    }

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][config_entry.entry_id] = backup_agent

    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)

    # Verify token is redacted
    assert diagnostics["config"][CONF_TOKEN] != "secret_oauth_token_abc123"
    assert "REDACTED" in str(diagnostics["config"][CONF_TOKEN])
    assert "secret" not in str(diagnostics["config"][CONF_TOKEN])
