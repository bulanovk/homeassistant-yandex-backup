"""Tests for Yandex Disk config flow."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from yadisk.exceptions import UnauthorizedError, YaDiskError

from custom_components.yandex_disk_backup import config_flow
from custom_components.yandex_disk_backup.const import (
    CONF_BACKUP_FOLDER,
    CONF_TOKEN,
    DEFAULT_BACKUP_FOLDER,
)


@pytest.mark.asyncio
async def test_config_flow_valid_token(hass: HomeAssistant):
    """Test config flow with valid token."""
    # Create config flow instance
    flow = config_flow.YandexDiskConfigFlow()
    flow.hass = hass
    # Set _context to make it mutable
    flow._context = {}

    with patch(
        "custom_components.yandex_disk_backup.config_flow._async_validate_token",
        return_value=True,
    ):
        # Mock async_set_unique_id to avoid context modification issues
        with patch.object(flow, "async_set_unique_id"):
            # Initialize the flow (should show form)
            result = await flow.async_step_user()
            assert result["type"] == FlowResultType.FORM
            assert result["step_id"] == "user"

            # Submit valid token
            result = await flow.async_step_user(
                {
                    CONF_TOKEN: "valid_token_abc123",
                    CONF_BACKUP_FOLDER: "/backups",
                }
            )

            assert result["type"] == FlowResultType.CREATE_ENTRY
            assert result["title"] == "Yandex Disk"
            assert result["data"][CONF_TOKEN] == "valid_token_abc123"
            assert result["data"][CONF_BACKUP_FOLDER] == "/backups"


@pytest.mark.asyncio
async def test_config_flow_invalid_token(hass: HomeAssistant):
    """Test config flow with invalid token."""
    flow = config_flow.YandexDiskConfigFlow()
    flow.hass = hass
    flow._context = {}

    with patch(
        "custom_components.yandex_disk_backup.config_flow._async_validate_token",
        return_value=False,
    ):
        with patch.object(flow, "async_set_unique_id"):
            # Submit invalid token
            result = await flow.async_step_user(
                {
                    CONF_TOKEN: "invalid_token",
                    CONF_BACKUP_FOLDER: DEFAULT_BACKUP_FOLDER,
                }
            )

            assert result["type"] == FlowResultType.FORM
            assert result["errors"]["base"] == "invalid_token"


@pytest.mark.asyncio
async def test_config_flow_api_error(hass: HomeAssistant):
    """Test config flow with API error."""
    flow = config_flow.YandexDiskConfigFlow()
    flow.hass = hass
    flow._context = {}

    with patch(
        "custom_components.yandex_disk_backup.config_flow._async_validate_token",
        return_value=False,
    ):
        with patch.object(flow, "async_set_unique_id"):
            # Submit token that causes API error
            result = await flow.async_step_user(
                {
                    CONF_TOKEN: "error_token",
                    CONF_BACKUP_FOLDER: DEFAULT_BACKUP_FOLDER,
                }
            )

            assert result["type"] == FlowResultType.FORM
            assert result["errors"]["base"] == "invalid_token"


@pytest.mark.asyncio
async def test_config_flow_default_backup_folder(hass: HomeAssistant):
    """Test config flow with default backup folder."""
    flow = config_flow.YandexDiskConfigFlow()
    flow.hass = hass
    flow._context = {}

    with patch(
        "custom_components.yandex_disk_backup.config_flow._async_validate_token",
        return_value=True,
    ):
        with patch.object(flow, "async_set_unique_id"):
            # Submit without specifying backup folder (should use default)
            result = await flow.async_step_user(
                {
                    CONF_TOKEN: "valid_token",
                }
            )

            assert result["type"] == FlowResultType.CREATE_ENTRY
            assert result["data"][CONF_BACKUP_FOLDER] == DEFAULT_BACKUP_FOLDER


@pytest.mark.asyncio
async def test_config_flow_already_configured(hass: HomeAssistant):
    """Test config flow when account is already configured."""
    flow = config_flow.YandexDiskConfigFlow()
    flow.hass = hass
    flow._context = {}

    # Set up unique_id that already exists
    existing_unique_id = "token_ab"

    with patch(
        "custom_components.yandex_disk_backup.config_flow._async_validate_token",
        return_value=True,
    ):
        # Mock async_set_unique_id to set the unique_id and check for existing entries
        async def mock_set_unique_id(unique_id=None):
            if unique_id == existing_unique_id:
                # Simulate already configured
                from homeassistant.data_entry_flow import AbortFlow
                raise AbortFlow("already_configured")
            flow._unique_id = unique_id

        with patch.object(flow, "async_set_unique_id", side_effect=mock_set_unique_id):
            # Submit token for already configured account
            from homeassistant.data_entry_flow import AbortFlow
            with pytest.raises(AbortFlow) as exc_info:
                await flow.async_step_user(
                    {
                        CONF_TOKEN: "token_abcdefgh",  # Same first 8 chars as existing
                        CONF_BACKUP_FOLDER: DEFAULT_BACKUP_FOLDER,
                    }
                )

            assert exc_info.value.reason == "already_configured"


@pytest.mark.asyncio
async def test_token_validation_function(hass: HomeAssistant):
    """Test the token validation function directly."""
    with patch("custom_components.yandex_disk_backup.config_flow.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get_disk_info = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Valid token
        is_valid = await config_flow._async_validate_token(hass, "valid_token")
        assert is_valid is True


@pytest.mark.asyncio
async def test_token_validation_unauthorized(hass: HomeAssistant):
    """Test token validation with unauthorized error."""
    with patch("custom_components.yandex_disk_backup.config_flow.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get_disk_info.side_effect = UnauthorizedError("Invalid token")
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Invalid token
        is_valid = await config_flow._async_validate_token(hass, "invalid_token")
        assert is_valid is False


@pytest.mark.asyncio
async def test_reauth_flow_success(hass: HomeAssistant):
    """Test successful reauthentication flow."""
    flow = config_flow.YandexDiskConfigFlow()
    flow.hass = hass
    flow._context = {}

    # Set up reauth context
    old_token = "old_token_abc123"

    with patch(
        "custom_components.yandex_disk_backup.config_flow._async_validate_token",
        return_value=True,
    ):
        with patch.object(flow, "async_set_unique_id"):
            # Initiate reauth flow
            result = await flow.async_step_reauth(
                {
                    CONF_TOKEN: old_token,
                    CONF_BACKUP_FOLDER: "/backups",
                }
            )

            assert result["type"] == FlowResultType.FORM
            assert result["step_id"] == "reauth_confirm"

            # Submit new valid token
            result = await flow.async_step_reauth_confirm(
                {CONF_TOKEN: "new_token_xyz789"}
            )

            assert result["type"] == FlowResultType.ABORT
            assert result["reason"] == "reauth_successful"


@pytest.mark.asyncio
async def test_reauth_flow_invalid_token(hass: HomeAssistant):
    """Test reauthentication flow with invalid token."""
    flow = config_flow.YandexDiskConfigFlow()
    flow.hass = hass
    flow._context = {}

    # Set up reauth context
    old_token = "old_token"

    with patch(
        "custom_components.yandex_disk_backup.config_flow._async_validate_token",
        return_value=False,
    ):
        with patch.object(flow, "async_set_unique_id"):
            # Initiate reauth flow
            result = await flow.async_step_reauth(
                {
                    CONF_TOKEN: old_token,
                    CONF_BACKUP_FOLDER: DEFAULT_BACKUP_FOLDER,
                }
            )

            # Submit invalid token
            result = await flow.async_step_reauth_confirm(
                {CONF_TOKEN: "invalid_token"}
            )

            assert result["type"] == FlowResultType.FORM
            assert result["step_id"] == "reauth_confirm"
            assert result["errors"]["base"] == "invalid_token"
