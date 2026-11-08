"""Yandex OAuth client: token refresh for PKCE (built-in app) entries."""

import asyncio
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import aiohttp

from .const import OAUTH_TOKEN_URL

_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


@dataclass(frozen=True)
class TokenSet:
    """Tokens returned by Yandex, with absolute expiry time."""

    access_token: str
    refresh_token: str | None
    expires_at: float
    scope: str | None


class OAuthError(Exception):
    """Base error for OAuth operations. Never contains tokens."""

    def __init__(self, code: str, description: str = "") -> None:
        """Store the Yandex error code."""
        super().__init__(f"{code}: {description}" if description else code)
        self.code = code


class OAuthInvalidGrant(OAuthError):
    """Refresh token rejected; the user must authorize again."""


class OAuthInvalidClient(OAuthError):
    """Client id/secret rejected by Yandex."""


class OAuthConnectionError(OAuthError):
    """Network failure or unusable response from Yandex."""


def _map_error(payload: Mapping[str, Any]) -> OAuthError:
    code = str(payload.get("error", "unknown_error"))
    description = str(payload.get("error_description", ""))
    if code == "invalid_grant":
        return OAuthInvalidGrant(code, description)
    if code in ("invalid_client", "unauthorized_client"):
        return OAuthInvalidClient(code, description)
    return OAuthError(code, description)


class YandexOAuthClient:
    """Minimal async client for Yandex OAuth endpoints using HA's aiohttp session."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        client_id: str,
        *,
        now: Callable[[], float] = time.time,
    ) -> None:
        """Create the client for the built-in public (PKCE) app."""
        self._session = session
        self._client_id = client_id
        self._now = now

    async def _post(
        self, url: str, data: Mapping[str, str]
    ) -> tuple[int, dict[str, Any]]:
        """POST form data with the client id in the body; return (status, JSON object)."""
        # Public client (PKCE): no secret, the app identifies itself in the body.
        body = {**data, "client_id": self._client_id}
        try:
            async with self._session.post(
                url,
                data=body,
                timeout=_REQUEST_TIMEOUT,
            ) as resp:
                status = resp.status
                try:
                    payload: Any = await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError):
                    payload = None
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise OAuthConnectionError("network_error", type(err).__name__) from err
        if status >= 500 or not isinstance(payload, dict):
            raise OAuthConnectionError("bad_response", f"HTTP {status}")
        return status, payload

    async def _exchange(self, data: Mapping[str, str]) -> TokenSet:
        status, payload = await self._post(OAUTH_TOKEN_URL, data)
        if status == 200 and "access_token" in payload:
            return TokenSet(
                access_token=str(payload["access_token"]),
                refresh_token=payload.get("refresh_token"),
                expires_at=self._now() + float(payload.get("expires_in", 0)),
                scope=payload.get("scope"),
            )
        raise _map_error(payload)

    async def refresh(self, refresh_token: str) -> TokenSet:
        """Exchange a refresh token for a new token set."""
        return await self._exchange(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}
        )
