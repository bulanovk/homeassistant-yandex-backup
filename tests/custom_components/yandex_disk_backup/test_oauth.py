"""Tests for the Yandex OAuth refresh client."""

import asyncio

import aiohttp
import pytest

from custom_components.yandex_disk_backup.const import OAUTH_TOKEN_URL
from custom_components.yandex_disk_backup.oauth import (
    OAuthConnectionError,
    OAuthInvalidClient,
    OAuthInvalidGrant,
    TokenSet,
    YandexOAuthClient,
)


class FakeResponse:
    def __init__(self, status, payload=None, json_error=None):
        self.status = status
        self._payload = payload
        self._json_error = json_error

    async def json(self, content_type=None):
        if self._json_error:
            raise self._json_error
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    def __init__(self, responses=(), error=None):
        self.responses = list(responses)
        self.error = error
        self.calls = []

    def post(self, url, data=None, auth=None, timeout=None):
        self.calls.append({"url": url, "data": data, "auth": auth})
        if self.error:
            raise self.error
        return self.responses.pop(0)


def _client(session, now=lambda: 1000.0):
    return YandexOAuthClient(session, "cid", now=now)


@pytest.mark.asyncio
async def test_refresh_success_sends_client_id_in_body():
    session = FakeSession([FakeResponse(200, {"access_token": "B", "expires_in": 10})])
    token = await _client(session).refresh("R1")
    assert token == TokenSet("B", None, 1010.0, None)
    call = session.calls[0]
    assert call["url"] == OAUTH_TOKEN_URL
    assert call["auth"] is None
    assert call["data"] == {
        "grant_type": "refresh_token",
        "refresh_token": "R1",
        "client_id": "cid",
    }


@pytest.mark.asyncio
async def test_refresh_invalid_grant():
    session = FakeSession([FakeResponse(400, {"error": "invalid_grant"})])
    with pytest.raises(OAuthInvalidGrant):
        await _client(session).refresh("R1")


@pytest.mark.asyncio
async def test_refresh_invalid_client():
    session = FakeSession([FakeResponse(400, {"error": "invalid_client"})])
    with pytest.raises(OAuthInvalidClient):
        await _client(session).refresh("R1")


@pytest.mark.asyncio
async def test_server_error_html_is_connection_error():
    session = FakeSession(
        [FakeResponse(502, None, json_error=aiohttp.ContentTypeError(None, None))]
    )
    with pytest.raises(OAuthConnectionError):
        await _client(session).refresh("R1")


@pytest.mark.asyncio
async def test_client_error_is_connection_error():
    session = FakeSession(error=aiohttp.ClientError("boom"))
    with pytest.raises(OAuthConnectionError):
        await _client(session).refresh("R1")


@pytest.mark.asyncio
async def test_timeout_is_connection_error():
    session = FakeSession(error=asyncio.TimeoutError())
    with pytest.raises(OAuthConnectionError):
        await _client(session).refresh("R1")
