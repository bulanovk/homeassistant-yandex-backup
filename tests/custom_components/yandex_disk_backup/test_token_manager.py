"""Tests for the token manager."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.yandex_disk_backup.const import TOKEN_REFRESH_MARGIN
from custom_components.yandex_disk_backup.oauth import (
    OAuthConnectionError,
    OAuthInvalidGrant,
    TokenSet,
)
from custom_components.yandex_disk_backup.token_manager import (
    TokenManager,
    TokenNetworkError,
    TokenRefreshError,
)

NOW = 1_000_000.0
DAY = 24 * 3600


def _entry(expires_in_days: float):
    entry = Mock()
    entry.data = {
        "token": "A",
        "refresh_token": "R",
        "expires_at": NOW + expires_in_days * DAY,
    }
    entry.async_start_reauth = Mock()
    return entry


def _hass(entry):
    hass = Mock()

    def update(target, data):
        target.data = data

    hass.config_entries.async_update_entry = Mock(side_effect=update)
    return hass


def _manager(entry, oauth):
    return TokenManager(_hass(entry), entry, oauth, now=lambda: NOW)


@pytest.mark.asyncio
async def test_fresh_token_no_refresh():
    entry = _entry(60)
    oauth = AsyncMock()
    assert await _manager(entry, oauth).async_get_access_token() == "A"
    oauth.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_near_expiry_persists_new_tokens():
    entry = _entry(10)
    oauth = AsyncMock()
    oauth.refresh.return_value = TokenSet("B", "R2", NOW + 365 * DAY, None)
    hass = _hass(entry)
    manager = TokenManager(hass, entry, oauth, now=lambda: NOW)

    assert await manager.async_get_access_token() == "B"
    oauth.refresh.assert_awaited_once_with("R")
    stored = hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert stored["token"] == "B"
    assert stored["refresh_token"] == "R2"
    assert stored["expires_at"] == NOW + 365 * DAY


@pytest.mark.asyncio
async def test_refresh_keeps_old_refresh_token_when_absent():
    entry = _entry(10)
    oauth = AsyncMock()
    oauth.refresh.return_value = TokenSet("B", None, NOW + 365 * DAY, None)
    await _manager(entry, oauth).async_get_access_token()
    assert entry.data["refresh_token"] == "R"


@pytest.mark.asyncio
async def test_invalid_grant_starts_reauth():
    entry = _entry(10)
    oauth = AsyncMock()
    oauth.refresh.side_effect = OAuthInvalidGrant("invalid_grant")
    with pytest.raises(TokenRefreshError):
        await _manager(entry, oauth).async_get_access_token()
    entry.async_start_reauth.assert_called_once()


@pytest.mark.asyncio
async def test_network_error_with_still_valid_token_returns_it():
    entry = _entry(1)
    oauth = AsyncMock()
    oauth.refresh.side_effect = OAuthConnectionError("network_error")
    assert await _manager(entry, oauth).async_get_access_token() == "A"


@pytest.mark.asyncio
async def test_network_error_with_expired_token_raises_network_error():
    entry = _entry(-1)
    oauth = AsyncMock()
    oauth.refresh.side_effect = OAuthConnectionError("network_error")
    with pytest.raises(TokenNetworkError):
        await _manager(entry, oauth).async_get_access_token()


@pytest.mark.asyncio
async def test_concurrent_callers_refresh_once():
    entry = _entry(10)
    oauth = AsyncMock()

    async def slow_refresh(_refresh_token):
        await asyncio.sleep(0)
        return TokenSet("B", "R2", NOW + 365 * DAY, None)

    oauth.refresh.side_effect = slow_refresh
    manager = _manager(entry, oauth)

    results = await asyncio.gather(
        manager.async_get_access_token(), manager.async_get_access_token()
    )
    assert results == ["B", "B"]
    oauth.refresh.assert_awaited_once()
    assert TOKEN_REFRESH_MARGIN < NOW + 365 * DAY - NOW
