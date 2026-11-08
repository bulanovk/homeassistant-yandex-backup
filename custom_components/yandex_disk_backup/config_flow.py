"""Config flow for Yandex Disk backup integration."""

import logging
from collections.abc import Mapping
from typing import Any, Self

import voluptuous as vol  # type: ignore[import-untyped]
from yadisk import AsyncClient
from yadisk.exceptions import ForbiddenError, UnauthorizedError, YaDiskError

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    APP_CLIENT_ID,
    AUTH_METHOD_MANUAL,
    AUTH_METHOD_OAUTH,
    CONF_AUTH_METHOD,
    CONF_BACKUP_FOLDER,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_DEVICE_ID,
    CONF_EXPIRES_AT,
    CONF_INSTANCE_FOLDER,
    CONF_REFRESH_TOKEN,
    CONF_STORAGE_MODE,
    CONF_TOKEN,
    DEFAULT_BACKUP_FOLDER,
    DOMAIN,
    OAUTH_AUTHORIZE_URL,
    OAUTH_TOKEN_URL,
    SCOPES_APP_FOLDER,
    STORAGE_MODE_APP_FOLDER,
    STORAGE_MODE_DISK_FOLDER,
    _LOGGER,
)
from .paths import (
    InvalidPathError,
    make_unique_id,
    resolve_base_path,
    validate_instance_folder,
)
from .storage import FolderIsFileError, async_ensure_folder

# Keys that belong to the legacy device flow or to a previous token; they are
# dropped whenever an entry is reauthenticated with a new token.
_LEGACY_AUTH_KEYS = (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_DEVICE_ID,
    CONF_REFRESH_TOKEN,
    CONF_EXPIRES_AT,
)

STEP_CHOICE_SCHEMA = vol.Schema(
    {
        vol.Required(
            CONF_STORAGE_MODE, default=STORAGE_MODE_APP_FOLDER
        ): SelectSelector(
            SelectSelectorConfig(
                options=[STORAGE_MODE_APP_FOLDER, STORAGE_MODE_DISK_FOLDER],
                mode=SelectSelectorMode.LIST,
                translation_key="storage_mode",
            )
        ),
    }
)

STEP_MANUAL_TOKEN_SCHEMA = vol.Schema({vol.Required(CONF_TOKEN): str})


async def _async_check_access(
    hass: HomeAssistant, token: str, base_path: str | None
) -> str:
    """Verify the token, optionally create the base folder, return the account uid.

    Raises:
        YaDiskError / FolderIsFileError: propagated to the caller for mapping
    """

    def _create_client() -> AsyncClient:
        """Create AsyncClient - may block on SSL context initialization."""
        return AsyncClient(token=token)

    client = await hass.async_add_executor_job(_create_client)
    async with client as client_ctx:
        info = await client_ctx.get_disk_info()
        if base_path is not None:
            await async_ensure_folder(client_ctx, base_path)
        return str(info.user.uid)


def _map_error(err: Exception) -> str:
    """Map an exception from the access check to a form error key."""
    if isinstance(err, (UnauthorizedError, ForbiddenError)):
        return "invalid_token"
    if isinstance(err, FolderIsFileError):
        return "folder_is_file"
    if isinstance(err, YaDiskError):
        _LOGGER.warning("Yandex Disk request failed: %s", type(err).__name__)
        return "cannot_connect"
    _LOGGER.exception("Unexpected error during Yandex Disk setup")
    return "unknown"


def _data_without_legacy_auth(entry: config_entries.ConfigEntry) -> dict[str, Any]:
    """Return the entry data without legacy device-flow and token keys."""
    return {k: v for k, v in entry.data.items() if k not in _LEGACY_AUTH_KEYS}


class YandexPkceImplementation(
    config_entry_oauth2_flow.LocalOAuth2ImplementationWithPkce
):
    """Yandex OAuth with PKCE for the built-in public app (no client secret)."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Create the implementation for the built-in app."""
        super().__init__(
            hass, DOMAIN, APP_CLIENT_ID, OAUTH_AUTHORIZE_URL, OAUTH_TOKEN_URL
        )

    @property
    def name(self) -> str:
        """Name shown if several implementations exist."""
        return "Yandex"

    @property
    def extra_authorize_data(self) -> dict:
        """Request exactly the app-folder scopes on top of the PKCE challenge."""
        return {"scope": " ".join(SCOPES_APP_FOLDER), **super().extra_authorize_data}


class YandexDiskConfigFlow(  # type: ignore[call-arg]
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Yandex Disk config flow."""

    DOMAIN = DOMAIN
    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow state."""
        super().__init__()
        self._storage_mode: str = STORAGE_MODE_APP_FOLDER
        self._auth_data: dict[str, Any] = {}
        self._reconfigure_pending: tuple[str, str, dict[str, Any]] | None = None

    @property
    def logger(self) -> logging.Logger:
        """Logger used by the OAuth2 flow helper."""
        return _LOGGER

    def is_matching(self, other_flow: Self) -> bool:  # pylint: disable=unused-argument
        """Return False; flows are matched by unique_id only."""
        return False

    async def async_step_user(
        self,
        user_input: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
        """Choose the storage mode."""
        if user_input is not None:
            self._storage_mode = user_input[CONF_STORAGE_MODE]
            if self._storage_mode == STORAGE_MODE_APP_FOLDER:
                # App folder: the built-in app with PKCE is the only sign-in.
                return await self._async_start_app_oauth()
            # Legacy full-disk folder: the built-in app cannot grant these scopes.
            return await self.async_step_manual_token()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_CHOICE_SCHEMA,
        )

    async def _async_start_app_oauth(self) -> ConfigFlowResult:
        """Sign in with the built-in app through Home Assistant's OAuth2 flow.

        A fresh implementation per flow gives each flow its own PKCE verifier.
        """
        config_entry_oauth2_flow.async_register_implementation(
            self.hass, DOMAIN, YandexPkceImplementation(self.hass)
        )
        return await self.async_step_pick_implementation()

    async def async_oauth_create_entry(self, data: dict) -> ConfigFlowResult:
        """Store the token from the OAuth2 flow, then continue setup or reauth."""
        token = data["token"]
        self._auth_data = {
            CONF_TOKEN: token["access_token"],
            CONF_REFRESH_TOKEN: token.get("refresh_token"),
            CONF_EXPIRES_AT: token["expires_at"],
            CONF_AUTH_METHOD: AUTH_METHOD_OAUTH,
        }
        if self.source == config_entries.SOURCE_REAUTH:
            return await self.async_step_reauth_oauth_finish()
        return await self.async_step_folder()

    async def async_step_manual_token(
        self,
        user_input: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
        """Accept a manually created OAuth token (regular Disk folder)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            try:
                await _async_check_access(self.hass, token, None)
            except Exception as err:  # pylint: disable=broad-exception-caught
                errors["base"] = _map_error(err)
            else:
                self._auth_data = {
                    CONF_TOKEN: token,
                    CONF_AUTH_METHOD: AUTH_METHOD_MANUAL,
                }
                return await self.async_step_folder()

        return self.async_show_form(
            step_id="manual_token",
            data_schema=STEP_MANUAL_TOKEN_SCHEMA,
            errors=errors,
        )

    def _reconfigure_entry(self) -> config_entries.ConfigEntry | None:
        """Return the entry being reconfigured, or None for a new entry."""
        if self.source != config_entries.SOURCE_RECONFIGURE:
            return None
        return self._get_reconfigure_entry()

    def _suggest_instance_folder(self) -> str:
        """Suggest the location name, made unique among other entries.

        Reconfiguring keeps the entry's current folder: its own name is neither
        suffixed nor counted as taken.
        """
        own = self._reconfigure_entry()
        if own is not None and own.data.get(CONF_INSTANCE_FOLDER):
            return str(own.data[CONF_INSTANCE_FOLDER])
        base = self.hass.config.location_name.strip()
        try:
            validate_instance_folder(base)
        except InvalidPathError:
            base = "Home"
        taken = {
            entry.data.get(CONF_INSTANCE_FOLDER)
            for entry in self._async_current_entries()
            if own is None or entry.entry_id != own.entry_id
        }
        name, number = base, 2
        while name in taken:
            name = f"{base} {number}"
            number += 1
        return name

    def _suggest_backup_folder(self) -> str:
        """Suggest the disk folder; reconfiguring keeps the entry's current one."""
        own = self._reconfigure_entry()
        if own is not None and own.data.get(CONF_BACKUP_FOLDER):
            return str(own.data[CONF_BACKUP_FOLDER])
        return DEFAULT_BACKUP_FOLDER

    async def async_step_folder(
        self,
        user_input: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
        """Choose the backup folder and create the entry."""
        is_app = self._storage_mode == STORAGE_MODE_APP_FOLDER
        key = CONF_INSTANCE_FOLDER if is_app else CONF_BACKUP_FOLDER
        errors: dict[str, str] = {}
        if user_input is not None:
            suggested = user_input[key]
        elif is_app:
            suggested = self._suggest_instance_folder()
        else:
            suggested = self._suggest_backup_folder()
        schema = vol.Schema({vol.Required(key, default=suggested): cv.string})

        if user_input is not None:
            folder = user_input[key].strip()
            base_path: str | None = None
            try:
                if is_app:
                    validate_instance_folder(folder)
                    base_path = resolve_base_path(
                        {CONF_STORAGE_MODE: self._storage_mode, key: folder}
                    )
                else:
                    folder = folder or DEFAULT_BACKUP_FOLDER
            except InvalidPathError:
                errors[key] = "invalid_instance_folder"

            if not errors:
                try:
                    uid = await _async_check_access(
                        self.hass, self._auth_data[CONF_TOKEN], base_path
                    )
                except Exception as err:  # pylint: disable=broad-exception-caught
                    errors["base"] = _map_error(err)
                else:
                    if self._auth_data.get(CONF_AUTH_METHOD) == AUTH_METHOD_MANUAL:
                        # Token entries keep the scheme used by the main branch.
                        unique_id = self._auth_data[CONF_TOKEN][:8]
                    else:
                        unique_id = make_unique_id(uid, self._storage_mode, folder)
                    title = f"Yandex Disk ({folder})"
                    data = {
                        **self._auth_data,
                        CONF_STORAGE_MODE: self._storage_mode,
                        key: folder,
                    }
                    if self.source == config_entries.SOURCE_RECONFIGURE:
                        return await self._async_finish_reconfigure(
                            unique_id, title, data
                        )
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title=title, data=data)

        return self.async_show_form(
            step_id="folder",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the storage mode of an existing entry (new sign-in required)."""
        return await self.async_step_user()

    async def _async_finish_reconfigure(
        self, unique_id: str, title: str, data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Replace the entry data; show a migration hint when the backup path changes."""
        entry = self._get_reconfigure_entry()
        for other in self._async_current_entries():
            if other.entry_id != entry.entry_id and other.unique_id == unique_id:
                return self.async_abort(reason="already_configured")
        if resolve_base_path(entry.data) == resolve_base_path(data):
            return self.async_update_reload_and_abort(
                entry, unique_id=unique_id, title=title, data=data
            )
        self._reconfigure_pending = (unique_id, title, data)
        return self.async_show_form(
            step_id="migration_hint",
            description_placeholders={
                "old_path": resolve_base_path(entry.data),
                "new_path": resolve_base_path(data),
            },
        )

    async def async_step_migration_hint(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Apply the reconfiguration after the user has read the hint."""
        pending = self._reconfigure_pending
        if pending is None:
            return self.async_abort(reason="cannot_connect")
        unique_id, title, data = pending
        if user_input is None:
            return self.async_show_form(
                step_id="migration_hint",
                description_placeholders={
                    "old_path": resolve_base_path(self._get_reconfigure_entry().data),
                    "new_path": resolve_base_path(data),
                },
            )
        return self.async_update_reload_and_abort(
            self._get_reconfigure_entry(),
            unique_id=unique_id,
            title=title,
            data=data,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication.

        App-folder entries sign in through PKCE, because the built-in app is the
        only sign-in for that mode. Legacy disk-folder entries use a manually
        created token.
        """
        mode = entry_data.get(CONF_STORAGE_MODE)
        method = entry_data.get(CONF_AUTH_METHOD)
        if method == AUTH_METHOD_OAUTH or mode == STORAGE_MODE_APP_FOLDER:
            return await self.async_step_reauth_oauth()
        return await self.async_step_reauth_confirm()

    async def _async_ensure_same_account(self, uid: str) -> None:
        """Abort if the new token belongs to another account or folder.

        Legacy entries (no storage_mode) have no stable identity, so they are
        accepted for any account.
        """
        entry = self._get_reauth_entry()
        mode = entry.data.get(CONF_STORAGE_MODE)
        if mode is None:
            return
        if mode == STORAGE_MODE_APP_FOLDER:
            folder = entry.data.get(CONF_INSTANCE_FOLDER, "")
        else:
            folder = entry.data.get(CONF_BACKUP_FOLDER, DEFAULT_BACKUP_FOLDER)
        await self.async_set_unique_id(make_unique_id(uid, mode, folder))
        self._abort_if_unique_id_mismatch(reason="wrong_account")

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reauthenticate a manual-token entry with a new token."""
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            try:
                await _async_check_access(self.hass, token, None)
            except Exception as err:  # pylint: disable=broad-exception-caught
                errors["base"] = _map_error(err)
            else:
                entry = self._get_reauth_entry()
                return self.async_update_reload_and_abort(
                    entry,
                    data={
                        **_data_without_legacy_auth(entry),
                        CONF_TOKEN: token,
                        CONF_AUTH_METHOD: AUTH_METHOD_MANUAL,
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_MANUAL_TOKEN_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth_oauth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Sign in to Yandex again with the built-in app."""
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_oauth", data_schema=vol.Schema({})
            )
        return await self._async_start_app_oauth()

    async def async_step_reauth_oauth_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Verify the account of the new PKCE token and store it."""
        token = self._auth_data[CONF_TOKEN]
        try:
            uid = await _async_check_access(self.hass, token, None)
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOGGER.warning(
                "Cannot verify Yandex account after reauth: %s", _map_error(err)
            )
            return self.async_abort(reason="cannot_connect")
        await self._async_ensure_same_account(uid)
        entry = self._get_reauth_entry()
        return self.async_update_reload_and_abort(
            entry,
            data={
                **_data_without_legacy_auth(entry),
                **self._auth_data,
            },
        )
