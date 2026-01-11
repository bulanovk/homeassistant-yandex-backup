"""Config flow for Yandex Disk backup integration."""

from collections.abc import Mapping
from typing import Any, Self
import voluptuous as vol  # type: ignore[import-untyped]
from yadisk import AsyncClient
from yadisk.exceptions import UnauthorizedError, YaDiskError

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_BACKUP_FOLDER,
    CONF_TOKEN,
    DEFAULT_BACKUP_FOLDER,
    DOMAIN,
    _LOGGER,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TOKEN): str,
        vol.Optional(CONF_BACKUP_FOLDER, default=DEFAULT_BACKUP_FOLDER): cv.string,
    }
)


async def _async_validate_token(  # pylint: disable=unused-argument
    hass: HomeAssistant, token: str
) -> bool:
    """Validate OAuth token by checking Yandex Disk access.

    Args:
        hass: Home Assistant instance
        token: OAuth token to validate

    Returns:
        True if token is valid, False otherwise
    """

    def _create_client() -> AsyncClient:
        """Create AsyncClient - may block on SSL context initialization.

        Returns:
            The created AsyncClient instance
        """
        return AsyncClient(token=token)

    try:
        # Run client creation in executor to avoid blocking SSL calls
        client = await hass.async_add_executor_job(_create_client)
        async with client as client_ctx:
            # Try to get disk info to validate token
            await client_ctx.get_disk_info()
            return True
    except UnauthorizedError:
        _LOGGER.error("Invalid Yandex Disk token")
        return False
    except YaDiskError as err:
        _LOGGER.error("Token validation error: %s", err)
        return False
    except Exception:  # pylint: disable=broad-exception-caught
        _LOGGER.exception("Unexpected error validating token")
        return False


class YandexDiskConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Yandex Disk config flow."""

    VERSION = 1

    def is_matching(self, other_flow: Self) -> bool:  # pylint: disable=unused-argument
        """Check if another flow matches this flow.

        Args:
            other_flow: The other config flow to compare with

        Returns:
            True if the flows match, False otherwise
        """
        # For single-version flows, we only match if it's the same unique_id
        # which is handled by Home Assistant's base class logic
        return False

    async def async_step_user(
        self,
        user_input: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
        """Handle the initial step.

        Args:
            user_input: User input from the config flow form

        Returns:
            Config flow result (form, create_entry, or abort)
        """
        errors = {}

        if user_input is not None:
            # Validate token
            token_valid = await _async_validate_token(
                self.hass,
                user_input[CONF_TOKEN],
            )

            if not token_valid:
                errors["base"] = "invalid_token"
            else:
                # Use first 8 chars of token as unique_id
                await self.async_set_unique_id(user_input[CONF_TOKEN][:8])
                self._abort_if_unique_id_configured()

                # Ensure backup_folder has a value (use default if not provided)
                if CONF_BACKUP_FOLDER not in user_input:
                    user_input = dict(user_input)
                    user_input[CONF_BACKUP_FOLDER] = DEFAULT_BACKUP_FOLDER

                # Create config entry
                return self.async_create_entry(
                    title="Yandex Disk",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(  # pylint: disable=unused-argument
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauthentication when OAuth token expires.

        Args:
            entry_data: The existing config entry data

        Returns:
            Config flow result directing to reauth confirmation step
        """
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm and complete reauthentication.

        Args:
            user_input: User input from the reauth form (contains new token)

        Returns:
            Config flow result (abort if successful, form if validation fails)
        """
        errors = {}

        if user_input is not None:
            # Validate the new token
            token_valid = await _async_validate_token(
                self.hass,
                user_input[CONF_TOKEN],
            )

            if not token_valid:
                errors["base"] = "invalid_token"
            else:
                await self.async_set_unique_id(user_input[CONF_TOKEN][:8])
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
