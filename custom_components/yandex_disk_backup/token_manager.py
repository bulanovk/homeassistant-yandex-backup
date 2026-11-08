"""Access-token lifecycle for OAuth config entries (built-in PKCE app)."""

import asyncio
import time
from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_EXPIRES_AT,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN,
    TOKEN_REFRESH_MARGIN,
)
from .oauth import (
    OAuthConnectionError,
    OAuthError,
    OAuthInvalidClient,
    OAuthInvalidGrant,
    YandexOAuthClient,
)


class TokenRefreshError(Exception):
    """The access token is unusable and the user must reauthenticate."""


class TokenNetworkError(TokenRefreshError):
    """Refresh failed for a transient reason and the token already expired."""


class TokenManager:
    """Refresh the access token near expiry and persist it into the entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        oauth: YandexOAuthClient,
        *,
        now: Callable[[], float] = time.time,
    ) -> None:
        """Store collaborators; the lock serializes concurrent refreshes."""
        self._hass = hass
        self._entry = entry
        self._oauth = oauth
        self._now = now
        self._lock = asyncio.Lock()

    async def async_get_access_token(self) -> str:
        """Return a usable access token, refreshing it if it is close to expiry."""
        async with self._lock:
            # Re-read inside the lock: a concurrent caller may already have refreshed.
            data = self._entry.data
            expires_at = float(data.get(CONF_EXPIRES_AT, 0))
            if expires_at - self._now() >= TOKEN_REFRESH_MARGIN:
                return str(data[CONF_TOKEN])
            try:
                token = await self._oauth.refresh(data[CONF_REFRESH_TOKEN])
            except (OAuthInvalidGrant, OAuthInvalidClient) as err:
                self._entry.async_start_reauth(self._hass)
                raise TokenRefreshError(err.code) from err
            except OAuthError as err:
                if expires_at > self._now():
                    return str(data[CONF_TOKEN])
                if isinstance(err, OAuthConnectionError):
                    raise TokenNetworkError(err.code) from err
                raise TokenRefreshError(err.code) from err

            new_data = {
                **data,
                CONF_TOKEN: token.access_token,
                CONF_EXPIRES_AT: token.expires_at,
            }
            if token.refresh_token:
                new_data[CONF_REFRESH_TOKEN] = token.refresh_token
            self._hass.config_entries.async_update_entry(self._entry, data=new_data)
            return token.access_token
