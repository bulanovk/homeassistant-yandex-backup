"""Tests for Yandex Disk config flow."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant import config_entries
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import AbortFlow, FlowResultType
from yadisk.exceptions import (
    ForbiddenError,
    UnauthorizedError,
    YaDiskConnectionError,
    YaDiskError,
)

from custom_components.yandex_disk_backup import config_flow
from custom_components.yandex_disk_backup.const import (
    APP_CLIENT_ID,
    AUTH_METHOD_DEVICE,
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
    STORAGE_MODE_APP_FOLDER,
    STORAGE_MODE_DISK_FOLDER,
)
from custom_components.yandex_disk_backup.storage import FolderIsFileError

CHECK = "custom_components.yandex_disk_backup.config_flow._async_check_access"
REGISTER = (
    "custom_components.yandex_disk_backup.config_flow."
    "config_entry_oauth2_flow.async_register_implementation"
)
OAUTH_TOKEN = {
    "access_token": "A",
    "refresh_token": "R",
    "expires_in": 31536000,
    "expires_at": 9e9,
}
LEGACY_DEVICE_FIELDS = {
    CONF_AUTH_METHOD: AUTH_METHOD_DEVICE,
    CONF_CLIENT_ID: "cid",
    CONF_CLIENT_SECRET: "sec",
    CONF_DEVICE_ID: "dev",
}


def _flow(hass: HomeAssistant) -> config_flow.YandexDiskConfigFlow:
    flow = config_flow.YandexDiskConfigFlow()
    flow.hass = hass
    flow._context = {}
    flow._async_current_entries = lambda *_args, **_kwargs: []
    return flow


async def _to_manual_token(flow, storage_mode):
    """Enter the manual token step directly for the given storage mode."""
    flow._storage_mode = storage_mode
    result = await flow.async_step_manual_token()
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "manual_token"
    return result


async def _to_app_folder_step(flow):
    """Finish the PKCE sign-in for app-folder storage and stop at the folder step."""
    flow._storage_mode = STORAGE_MODE_APP_FOLDER
    result = await flow.async_oauth_create_entry(
        {"auth_implementation": DOMAIN, "token": dict(OAUTH_TOKEN)}
    )
    assert result["step_id"] == "folder"
    return result


@pytest.mark.asyncio
async def test_user_step_shows_form(hass: HomeAssistant):
    result = await _flow(hass).async_step_user()
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


@pytest.mark.asyncio
async def test_user_step_has_no_auth_choice(hass: HomeAssistant):
    result = await _flow(hass).async_step_user()
    assert CONF_AUTH_METHOD not in result["data_schema"].schema


@pytest.mark.asyncio
async def test_app_folder_starts_pkce_directly(hass: HomeAssistant):
    flow = _flow(hass)
    with patch(REGISTER) as register, patch.object(
        flow,
        "async_step_pick_implementation",
        AsyncMock(return_value={"type": "external"}),
    ) as pick:
        result = await flow.async_step_user(
            {CONF_STORAGE_MODE: STORAGE_MODE_APP_FOLDER}
        )
    assert result == {"type": "external"}
    pick.assert_awaited_once()
    impl = register.call_args.args[2]
    assert isinstance(impl, config_flow.YandexPkceImplementation)
    assert impl.client_id == APP_CLIENT_ID
    assert impl.client_secret == ""
    assert impl.domain == DOMAIN


@pytest.mark.asyncio
async def test_disk_folder_routes_straight_to_manual_token(hass: HomeAssistant):
    result = await _flow(hass).async_step_user(
        {CONF_STORAGE_MODE: STORAGE_MODE_DISK_FOLDER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "manual_token"


def test_pkce_authorize_data(hass: HomeAssistant):
    impl = config_flow.YandexPkceImplementation(hass)
    data = impl.extra_authorize_data
    assert data["scope"] == "cloud_api:disk.app_folder cloud_api:disk.info"
    assert data["code_challenge_method"] == "S256"
    assert data["code_challenge"]
    assert impl.name == "Yandex"


@pytest.mark.asyncio
async def test_oauth_token_goes_to_folder_and_drops_no_secrets(hass: HomeAssistant):
    flow = _flow(hass)
    flow._storage_mode = STORAGE_MODE_APP_FOLDER
    form = await flow.async_oauth_create_entry(
        {"auth_implementation": DOMAIN, "token": dict(OAUTH_TOKEN)}
    )
    assert form["step_id"] == "folder"
    with patch(CHECK, AsyncMock(return_value="42")), patch.object(
        flow, "async_set_unique_id"
    ):
        entry = await flow.async_step_folder({CONF_INSTANCE_FOLDER: "home"})
    data = entry["data"]
    assert data[CONF_AUTH_METHOD] == AUTH_METHOD_OAUTH
    assert data[CONF_TOKEN] == "A"
    assert data[CONF_REFRESH_TOKEN] == "R"
    assert data[CONF_EXPIRES_AT] == 9e9
    assert CONF_CLIENT_ID not in data
    assert CONF_CLIENT_SECRET not in data
    assert "auth_implementation" not in data


@pytest.mark.asyncio
async def test_manual_token_invalid(hass: HomeAssistant):
    flow = _flow(hass)
    await _to_manual_token(flow, STORAGE_MODE_DISK_FOLDER)
    with patch(CHECK, AsyncMock(side_effect=UnauthorizedError("bad"))):
        result = await flow.async_step_manual_token({CONF_TOKEN: "T"})
    assert result["step_id"] == "manual_token"
    assert result["errors"] == {"base": "invalid_token"}


@pytest.mark.asyncio
async def test_manual_token_connection_error(hass: HomeAssistant):
    flow = _flow(hass)
    await _to_manual_token(flow, STORAGE_MODE_DISK_FOLDER)
    with patch(CHECK, AsyncMock(side_effect=YaDiskConnectionError("down"))):
        result = await flow.async_step_manual_token({CONF_TOKEN: "T"})
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_manual_token_unexpected_error_is_unknown(hass: HomeAssistant):
    flow = _flow(hass)
    await _to_manual_token(flow, STORAGE_MODE_DISK_FOLDER)
    with patch(CHECK, AsyncMock(side_effect=RuntimeError("boom"))):
        result = await flow.async_step_manual_token({CONF_TOKEN: "T"})
    assert result["errors"] == {"base": "unknown"}


@pytest.mark.asyncio
async def test_app_folder_creates_entry(hass: HomeAssistant):
    flow = _flow(hass)
    await _to_app_folder_step(flow)
    check = AsyncMock(return_value="42")
    with patch(CHECK, check), patch.object(flow, "async_set_unique_id") as set_uid:
        result = await flow.async_step_folder({CONF_INSTANCE_FOLDER: "home"})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Yandex Disk (home)"
    assert result["data"] == {
        CONF_TOKEN: "A",
        CONF_REFRESH_TOKEN: "R",
        CONF_EXPIRES_AT: 9e9,
        CONF_AUTH_METHOD: AUTH_METHOD_OAUTH,
        CONF_STORAGE_MODE: STORAGE_MODE_APP_FOLDER,
        CONF_INSTANCE_FOLDER: "home",
    }
    set_uid.assert_called_once_with("42:app_folder:home")
    check.assert_awaited_with(hass, "A", "app:/home")


@pytest.mark.asyncio
async def test_app_folder_invalid_path_rejected_before_check(hass: HomeAssistant):
    flow = _flow(hass)
    await _to_app_folder_step(flow)
    check = AsyncMock(return_value="42")
    with patch(CHECK, check):
        result = await flow.async_step_folder({CONF_INSTANCE_FOLDER: "../x"})
    assert result["step_id"] == "folder"
    assert result["errors"] == {CONF_INSTANCE_FOLDER: "invalid_instance_folder"}
    check.assert_not_awaited()


@pytest.mark.asyncio
async def test_app_folder_file_in_the_way(hass: HomeAssistant):
    flow = _flow(hass)
    await _to_app_folder_step(flow)
    with patch(CHECK, AsyncMock(side_effect=FolderIsFileError("app:/home"))):
        result = await flow.async_step_folder({CONF_INSTANCE_FOLDER: "home"})
    assert result["errors"] == {"base": "folder_is_file"}


@pytest.mark.asyncio
async def test_disk_folder_creates_entry(hass: HomeAssistant):
    flow = _flow(hass)
    await _to_manual_token(flow, STORAGE_MODE_DISK_FOLDER)
    check = AsyncMock(return_value="42")
    with patch(CHECK, check), patch.object(flow, "async_set_unique_id") as set_uid:
        await flow.async_step_manual_token({CONF_TOKEN: "T"})
        result = await flow.async_step_folder(
            {CONF_BACKUP_FOLDER: DEFAULT_BACKUP_FOLDER}
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_BACKUP_FOLDER] == DEFAULT_BACKUP_FOLDER
    assert result["data"][CONF_STORAGE_MODE] == STORAGE_MODE_DISK_FOLDER
    assert check.await_args.args[2] is None
    set_uid.assert_called_once_with("T")


@pytest.mark.asyncio
async def test_already_configured_aborts(hass: HomeAssistant):
    flow = _flow(hass)
    await _to_app_folder_step(flow)
    with patch(CHECK, AsyncMock(return_value="42")), patch.object(
        flow, "async_set_unique_id"
    ), patch.object(
        flow,
        "_abort_if_unique_id_configured",
        side_effect=AbortFlow("already_configured"),
    ):
        with pytest.raises(AbortFlow):
            await flow.async_step_folder({CONF_INSTANCE_FOLDER: "home"})


@pytest.mark.asyncio
async def test_check_access_returns_uid_and_creates_folder():
    client = AsyncMock()
    info = Mock()
    info.user.uid = "777"
    client.get_disk_info.return_value = info
    client.__aenter__.return_value = client

    hass = Mock()

    async def run_executor(func, *args):
        return func(*args)

    hass.async_add_executor_job = run_executor

    with patch(
        "custom_components.yandex_disk_backup.config_flow.AsyncClient",
        return_value=client,
    ), patch(
        "custom_components.yandex_disk_backup.config_flow.async_ensure_folder",
        new=AsyncMock(),
    ) as ensure:
        uid = await config_flow._async_check_access(hass, "T", "app:/home")

    assert uid == "777"
    ensure.assert_awaited_once_with(client, "app:/home")


@pytest.mark.asyncio
async def test_check_access_without_base_skips_folder():
    client = AsyncMock()
    info = Mock()
    info.user.uid = "1"
    client.get_disk_info.return_value = info
    client.__aenter__.return_value = client
    hass = Mock()

    async def run_executor(func, *args):
        return func(*args)

    hass.async_add_executor_job = run_executor
    with patch(
        "custom_components.yandex_disk_backup.config_flow.AsyncClient",
        return_value=client,
    ), patch(
        "custom_components.yandex_disk_backup.config_flow.async_ensure_folder",
        new=AsyncMock(),
    ) as ensure:
        await config_flow._async_check_access(hass, "T", None)
    ensure.assert_not_awaited()


def test_map_error_keys():
    assert config_flow._map_error(UnauthorizedError("x")) == "invalid_token"
    assert config_flow._map_error(ForbiddenError("x")) == "invalid_token"
    assert config_flow._map_error(FolderIsFileError("p")) == "folder_is_file"
    assert config_flow._map_error(YaDiskError("x")) == "cannot_connect"
    assert config_flow._map_error(ValueError("x")) == "unknown"


# ---------------------------------------------------------------------------
# Reauthentication
# ---------------------------------------------------------------------------


def _reauth_flow(hass: HomeAssistant, data: dict):
    flow = _flow(hass)
    flow.flow_id = "flow-r"
    flow.context = {"source": SOURCE_REAUTH, "entry_id": "e1"}
    entry = Mock()
    entry.data = data
    flow._get_reauth_entry = Mock(return_value=entry)
    flow.async_update_reload_and_abort = Mock(return_value={"type": "abort"})
    return flow


@pytest.mark.asyncio
async def test_reauth_confirm_invalid_token(hass: HomeAssistant):
    flow = _reauth_flow(hass, {CONF_TOKEN: "old"})
    with patch(CHECK, AsyncMock(side_effect=UnauthorizedError("bad"))):
        result = await flow.async_step_reauth_confirm({CONF_TOKEN: "new"})
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "invalid_token"}
    flow.async_update_reload_and_abort.assert_not_called()


@pytest.mark.asyncio
async def test_reauth_manual_saves_token(hass: HomeAssistant):
    flow = _reauth_flow(
        hass,
        {
            CONF_TOKEN: "old",
            CONF_STORAGE_MODE: STORAGE_MODE_DISK_FOLDER,
            CONF_BACKUP_FOLDER: "/HA",
        },
    )
    with patch(CHECK, AsyncMock(return_value="42")), patch.object(
        flow, "async_set_unique_id", AsyncMock()
    ) as set_uid, patch.object(flow, "_abort_if_unique_id_mismatch"):
        await flow.async_step_reauth_confirm({CONF_TOKEN: " NEW "})
    set_uid.assert_not_awaited()
    flow.async_update_reload_and_abort.assert_called_once()
    assert flow.async_update_reload_and_abort.call_args.kwargs["data"] == {
        CONF_TOKEN: "NEW",
        CONF_AUTH_METHOD: AUTH_METHOD_MANUAL,
        CONF_STORAGE_MODE: STORAGE_MODE_DISK_FOLDER,
        CONF_BACKUP_FOLDER: "/HA",
    }


@pytest.mark.asyncio
async def test_reauth_manual_legacy_entry_skips_identity(hass: HomeAssistant):
    flow = _reauth_flow(hass, {CONF_TOKEN: "old", CONF_BACKUP_FOLDER: "/x"})
    with patch(CHECK, AsyncMock(return_value="42")), patch.object(
        flow, "async_set_unique_id", AsyncMock()
    ) as set_uid, patch.object(flow, "_abort_if_unique_id_mismatch") as mismatch:
        await flow.async_step_reauth_confirm({CONF_TOKEN: "NEW"})
    set_uid.assert_not_awaited()
    mismatch.assert_not_called()
    kwargs = flow.async_update_reload_and_abort.call_args.kwargs
    assert kwargs["data"][CONF_TOKEN] == "NEW"
    assert kwargs["data"][CONF_BACKUP_FOLDER] == "/x"


@pytest.mark.asyncio
async def test_reauth_manual_disk_entry_ignores_account_change(hass: HomeAssistant):
    """Token entries keep the main-branch behaviour: no account identity check."""
    flow = _reauth_flow(
        hass,
        {
            CONF_TOKEN: "old",
            CONF_STORAGE_MODE: STORAGE_MODE_DISK_FOLDER,
            CONF_BACKUP_FOLDER: "/HA",
        },
    )
    with patch(CHECK, AsyncMock(return_value="99")), patch.object(
        flow, "async_set_unique_id", AsyncMock()
    ) as set_uid, patch.object(flow, "_abort_if_unique_id_mismatch") as mismatch:
        await flow.async_step_reauth_confirm({CONF_TOKEN: "NEW"})
    set_uid.assert_not_awaited()
    mismatch.assert_not_called()
    flow.async_update_reload_and_abort.assert_called_once()


@pytest.mark.asyncio
async def test_reauth_legacy_device_disk_folder_asks_for_token(hass: HomeAssistant):
    data = {
        CONF_TOKEN: "old",
        CONF_REFRESH_TOKEN: "oldr",
        CONF_EXPIRES_AT: 1.0,
        CONF_STORAGE_MODE: STORAGE_MODE_DISK_FOLDER,
        CONF_BACKUP_FOLDER: "/HA",
        **LEGACY_DEVICE_FIELDS,
    }
    flow = _reauth_flow(hass, data)
    form = await flow.async_step_reauth(data)
    assert form["step_id"] == "reauth_confirm"

    with patch(CHECK, AsyncMock(return_value="42")), patch.object(
        flow, "async_set_unique_id", AsyncMock()
    ), patch.object(flow, "_abort_if_unique_id_mismatch"):
        result = await flow.async_step_reauth_confirm({CONF_TOKEN: " NEW "})

    assert result == {"type": "abort"}
    assert flow.async_update_reload_and_abort.call_args.kwargs["data"] == {
        CONF_TOKEN: "NEW",
        CONF_AUTH_METHOD: AUTH_METHOD_MANUAL,
        CONF_STORAGE_MODE: STORAGE_MODE_DISK_FOLDER,
        CONF_BACKUP_FOLDER: "/HA",
    }


@pytest.mark.asyncio
async def test_reauth_legacy_device_app_folder_moves_to_pkce(hass: HomeAssistant):
    data = {
        CONF_TOKEN: "old",
        CONF_REFRESH_TOKEN: "oldr",
        CONF_EXPIRES_AT: 1.0,
        CONF_STORAGE_MODE: STORAGE_MODE_APP_FOLDER,
        CONF_INSTANCE_FOLDER: "home",
        **LEGACY_DEVICE_FIELDS,
    }
    flow = _reauth_flow(hass, data)
    with patch(REGISTER), patch.object(
        flow,
        "async_step_pick_implementation",
        AsyncMock(return_value={"type": "external"}),
    ), patch(CHECK, AsyncMock(return_value="42")), patch.object(
        flow, "async_set_unique_id", AsyncMock()
    ) as set_uid, patch.object(
        flow, "_abort_if_unique_id_mismatch"
    ):
        form = await flow.async_step_reauth(data)
        assert form["step_id"] == "reauth_oauth"
        assert await flow.async_step_reauth_oauth({}) == {"type": "external"}
        result = await flow.async_oauth_create_entry(
            {
                "auth_implementation": DOMAIN,
                "token": {**OAUTH_TOKEN, "access_token": "NEW", "refresh_token": "NR"},
            }
        )

    assert result == {"type": "abort"}
    set_uid.assert_awaited_once_with("42:app_folder:home")
    assert flow.async_update_reload_and_abort.call_args.kwargs["data"] == {
        CONF_TOKEN: "NEW",
        CONF_REFRESH_TOKEN: "NR",
        CONF_EXPIRES_AT: 9e9,
        CONF_AUTH_METHOD: AUTH_METHOD_OAUTH,
        CONF_STORAGE_MODE: STORAGE_MODE_APP_FOLDER,
        CONF_INSTANCE_FOLDER: "home",
    }


@pytest.mark.asyncio
async def test_reauth_manual_app_folder_entry_moves_to_pkce(hass: HomeAssistant):
    """App-folder storage has no manual token; old manual entries sign in again."""
    data = {
        CONF_TOKEN: "old",
        CONF_AUTH_METHOD: AUTH_METHOD_MANUAL,
        CONF_STORAGE_MODE: STORAGE_MODE_APP_FOLDER,
        CONF_INSTANCE_FOLDER: "home",
    }
    flow = _reauth_flow(hass, data)
    form = await flow.async_step_reauth(data)
    assert form["step_id"] == "reauth_oauth"


@pytest.mark.asyncio
async def test_reauth_oauth_entry_signs_in_again(hass: HomeAssistant):
    data = {
        CONF_TOKEN: "old",
        CONF_REFRESH_TOKEN: "oldr",
        CONF_AUTH_METHOD: AUTH_METHOD_OAUTH,
        CONF_STORAGE_MODE: STORAGE_MODE_APP_FOLDER,
        CONF_INSTANCE_FOLDER: "home",
        CONF_EXPIRES_AT: 1.0,
    }
    flow = _reauth_flow(hass, data)
    with patch(REGISTER), patch.object(
        flow,
        "async_step_pick_implementation",
        AsyncMock(return_value={"type": "external"}),
    ) as pick, patch(CHECK, AsyncMock(return_value="42")), patch.object(
        flow, "async_set_unique_id", AsyncMock()
    ) as set_uid, patch.object(
        flow, "_abort_if_unique_id_mismatch"
    ):
        form = await flow.async_step_reauth(data)
        assert form["step_id"] == "reauth_oauth"
        assert await flow.async_step_reauth_oauth({}) == {"type": "external"}
        pick.assert_awaited_once()
        result = await flow.async_oauth_create_entry(
            {
                "auth_implementation": DOMAIN,
                "token": {**OAUTH_TOKEN, "access_token": "NEW", "refresh_token": "NR"},
            }
        )
    assert result == {"type": "abort"}
    set_uid.assert_awaited_once_with("42:app_folder:home")
    assert flow.async_update_reload_and_abort.call_args.kwargs["data"] == {
        CONF_TOKEN: "NEW",
        CONF_REFRESH_TOKEN: "NR",
        CONF_EXPIRES_AT: 9e9,
        CONF_AUTH_METHOD: AUTH_METHOD_OAUTH,
        CONF_STORAGE_MODE: STORAGE_MODE_APP_FOLDER,
        CONF_INSTANCE_FOLDER: "home",
    }


@pytest.mark.asyncio
async def test_app_folder_suggests_location_name(hass: HomeAssistant):
    hass.config.location_name = "Дача"
    flow = _flow(hass)
    flow._storage_mode = STORAGE_MODE_APP_FOLDER
    flow._auth_data = {CONF_TOKEN: "T", CONF_AUTH_METHOD: AUTH_METHOD_MANUAL}
    result = await flow.async_step_folder()
    default = result["data_schema"].schema
    key = next(iter(default))
    assert key.default() == "Дача"


@pytest.mark.asyncio
async def test_app_folder_suggestion_skips_taken_names(hass: HomeAssistant):
    hass.config.location_name = "Home"
    flow = _flow(hass)
    flow._storage_mode = STORAGE_MODE_APP_FOLDER
    flow._auth_data = {CONF_TOKEN: "T", CONF_AUTH_METHOD: AUTH_METHOD_MANUAL}
    taken = Mock()
    taken.data = {CONF_INSTANCE_FOLDER: "Home"}
    with patch.object(flow, "_async_current_entries", return_value=[taken]):
        result = await flow.async_step_folder()
    key = next(iter(result["data_schema"].schema))
    assert key.default() == "Home 2"


# ---------------------------------------------------------------------------
# Reconfigure (storage mode change)
# ---------------------------------------------------------------------------


def _reconfigure_flow(hass: HomeAssistant, data: dict, others=()):
    flow = _flow(hass)
    flow.flow_id = "flow-c"
    flow.context = {"source": config_entries.SOURCE_RECONFIGURE, "entry_id": "e1"}
    entry = Mock()
    entry.entry_id = "e1"
    entry.data = data
    flow._get_reconfigure_entry = Mock(return_value=entry)
    flow._async_current_entries = lambda *_a, **_k: [*others]
    flow.async_update_reload_and_abort = Mock(return_value={"type": "abort"})
    return flow


@pytest.mark.asyncio
async def test_reconfigure_mode_change_shows_hint_and_replaces_data(
    hass: HomeAssistant,
):
    flow = _reconfigure_flow(
        hass,
        {
            CONF_TOKEN: "old",
            CONF_AUTH_METHOD: AUTH_METHOD_MANUAL,
            CONF_STORAGE_MODE: STORAGE_MODE_DISK_FOLDER,
            CONF_BACKUP_FOLDER: "/HA",
        },
    )
    flow._storage_mode = STORAGE_MODE_APP_FOLDER
    flow._auth_data = {CONF_TOKEN: "NEW", CONF_AUTH_METHOD: AUTH_METHOD_OAUTH}
    with patch(CHECK, AsyncMock(return_value="42")):
        hint = await flow.async_step_folder({CONF_INSTANCE_FOLDER: "home"})
    assert hint["step_id"] == "migration_hint"
    assert hint["description_placeholders"] == {
        "old_path": "/HA",
        "new_path": "app:/home",
    }
    flow.async_update_reload_and_abort.assert_not_called()

    result = await flow.async_step_migration_hint({})
    assert result == {"type": "abort"}
    kwargs = flow.async_update_reload_and_abort.call_args.kwargs
    assert flow.async_update_reload_and_abort.call_args.args[0].entry_id == "e1"
    assert kwargs["unique_id"] == "42:app_folder:home"
    assert kwargs["data"] == {
        CONF_TOKEN: "NEW",
        CONF_AUTH_METHOD: AUTH_METHOD_OAUTH,
        CONF_STORAGE_MODE: STORAGE_MODE_APP_FOLDER,
        CONF_INSTANCE_FOLDER: "home",
    }


@pytest.mark.asyncio
async def test_reconfigure_same_mode_skips_hint(hass: HomeAssistant):
    flow = _reconfigure_flow(
        hass,
        {
            CONF_TOKEN: "old",
            CONF_AUTH_METHOD: AUTH_METHOD_MANUAL,
            CONF_STORAGE_MODE: STORAGE_MODE_DISK_FOLDER,
            CONF_BACKUP_FOLDER: "/HA",
        },
    )
    flow._storage_mode = STORAGE_MODE_DISK_FOLDER
    flow._auth_data = {CONF_TOKEN: "NEW", CONF_AUTH_METHOD: AUTH_METHOD_MANUAL}
    with patch(CHECK, AsyncMock(return_value="42")):
        result = await flow.async_step_folder({CONF_BACKUP_FOLDER: "/HA"})
    assert result == {"type": "abort"}
    assert (
        flow.async_update_reload_and_abort.call_args.kwargs["data"][CONF_TOKEN] == "NEW"
    )


@pytest.mark.asyncio
async def test_reconfigure_same_mode_new_folder_shows_hint(hass: HomeAssistant):
    """Changing the folder moves the backup location, so the hint must appear."""
    flow = _reconfigure_flow(
        hass,
        {
            CONF_TOKEN: "old",
            CONF_AUTH_METHOD: AUTH_METHOD_MANUAL,
            CONF_STORAGE_MODE: STORAGE_MODE_DISK_FOLDER,
            CONF_BACKUP_FOLDER: "/HA",
        },
    )
    flow._storage_mode = STORAGE_MODE_DISK_FOLDER
    flow._auth_data = {CONF_TOKEN: "NEW", CONF_AUTH_METHOD: AUTH_METHOD_MANUAL}
    with patch(CHECK, AsyncMock(return_value="42")):
        hint = await flow.async_step_folder({CONF_BACKUP_FOLDER: "/HA2"})
    assert hint["step_id"] == "migration_hint"
    assert hint["description_placeholders"] == {
        "old_path": "/HA",
        "new_path": "/HA2",
    }
    flow.async_update_reload_and_abort.assert_not_called()


@pytest.mark.asyncio
async def test_reconfigure_legacy_entry_same_path_skips_hint(hass: HomeAssistant):
    """A legacy entry (no storage_mode) reconfigured to the same path moves nothing."""
    flow = _reconfigure_flow(
        hass,
        {
            CONF_TOKEN: "old",
            CONF_AUTH_METHOD: AUTH_METHOD_MANUAL,
            CONF_BACKUP_FOLDER: "/HA",
        },
    )
    flow._storage_mode = STORAGE_MODE_DISK_FOLDER
    flow._auth_data = {CONF_TOKEN: "NEW", CONF_AUTH_METHOD: AUTH_METHOD_MANUAL}
    with patch(CHECK, AsyncMock(return_value="42")):
        result = await flow.async_step_folder({CONF_BACKUP_FOLDER: "/HA"})
    assert result == {"type": "abort"}
    flow.async_update_reload_and_abort.assert_called_once()


@pytest.mark.asyncio
async def test_reconfigure_conflict_with_other_entry_aborts(hass: HomeAssistant):
    other = Mock()
    other.entry_id = "e2"
    other.unique_id = "42:app_folder:home"
    flow = _reconfigure_flow(
        hass,
        {
            CONF_TOKEN: "old",
            CONF_AUTH_METHOD: AUTH_METHOD_MANUAL,
            CONF_STORAGE_MODE: STORAGE_MODE_DISK_FOLDER,
            CONF_BACKUP_FOLDER: "/HA",
        },
        others=[other],
    )
    flow._storage_mode = STORAGE_MODE_APP_FOLDER
    flow._auth_data = {CONF_TOKEN: "NEW", CONF_AUTH_METHOD: AUTH_METHOD_OAUTH}
    with patch(CHECK, AsyncMock(return_value="42")):
        result = await flow.async_step_folder({CONF_INSTANCE_FOLDER: "home"})
    assert result["reason"] == "already_configured"
    flow.async_update_reload_and_abort.assert_not_called()


def _own_entry(data: dict) -> Mock:
    entry = Mock()
    entry.entry_id = "e1"
    entry.data = data
    return entry


def _folder_default(result: dict):
    return next(iter(result["data_schema"].schema)).default()


@pytest.mark.asyncio
async def test_reconfigure_app_folder_keeps_current_name(hass: HomeAssistant):
    """Re-running reconfigure must not add a suffix to the entry's own folder."""
    hass.config.location_name = "Home"
    data = {
        CONF_TOKEN: "old",
        CONF_AUTH_METHOD: AUTH_METHOD_OAUTH,
        CONF_STORAGE_MODE: STORAGE_MODE_APP_FOLDER,
        CONF_INSTANCE_FOLDER: "Home",
    }
    flow = _reconfigure_flow(hass, data, others=[_own_entry(data)])
    flow._storage_mode = STORAGE_MODE_APP_FOLDER
    result = await flow.async_step_folder()
    assert _folder_default(result) == "Home"


@pytest.mark.asyncio
async def test_reconfigure_to_app_folder_ignores_own_disk_entry(hass: HomeAssistant):
    hass.config.location_name = "Home"
    data = {
        CONF_TOKEN: "old",
        CONF_AUTH_METHOD: AUTH_METHOD_MANUAL,
        CONF_STORAGE_MODE: STORAGE_MODE_DISK_FOLDER,
        CONF_BACKUP_FOLDER: "/HA",
    }
    flow = _reconfigure_flow(hass, data, others=[_own_entry(data)])
    flow._storage_mode = STORAGE_MODE_APP_FOLDER
    result = await flow.async_step_folder()
    assert _folder_default(result) == "Home"


@pytest.mark.asyncio
async def test_reconfigure_suggestion_still_avoids_other_entries(hass: HomeAssistant):
    hass.config.location_name = "Home"
    data = {
        CONF_TOKEN: "old",
        CONF_AUTH_METHOD: AUTH_METHOD_MANUAL,
        CONF_STORAGE_MODE: STORAGE_MODE_DISK_FOLDER,
        CONF_BACKUP_FOLDER: "/HA",
    }
    other = Mock()
    other.entry_id = "e2"
    other.data = {CONF_INSTANCE_FOLDER: "Home"}
    flow = _reconfigure_flow(hass, data, others=[_own_entry(data), other])
    flow._storage_mode = STORAGE_MODE_APP_FOLDER
    result = await flow.async_step_folder()
    assert _folder_default(result) == "Home 2"


@pytest.mark.asyncio
async def test_reconfigure_disk_folder_keeps_current_path(hass: HomeAssistant):
    data = {
        CONF_TOKEN: "old",
        CONF_AUTH_METHOD: AUTH_METHOD_MANUAL,
        CONF_STORAGE_MODE: STORAGE_MODE_DISK_FOLDER,
        CONF_BACKUP_FOLDER: "/HA",
    }
    flow = _reconfigure_flow(hass, data, others=[_own_entry(data)])
    flow._storage_mode = STORAGE_MODE_DISK_FOLDER
    result = await flow.async_step_folder()
    assert _folder_default(result) == "/HA"
