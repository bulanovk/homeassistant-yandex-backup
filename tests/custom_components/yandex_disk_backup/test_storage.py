"""Tests for recursive folder creation."""

from unittest.mock import AsyncMock, Mock

import pytest
from yadisk.exceptions import PathExistsError, UnauthorizedError

from custom_components.yandex_disk_backup.storage import (
    FolderIsFileError,
    async_ensure_folder,
)


def _client(get_type: str = "dir") -> AsyncMock:
    client = AsyncMock()
    meta = Mock()
    meta.type = get_type
    client.get_meta.return_value = meta
    return client


@pytest.mark.asyncio
async def test_creates_each_level():
    client = _client()
    await async_ensure_folder(client, "app:/a/b")
    assert [c.args[0] for c in client.mkdir.await_args_list] == ["app:/a", "app:/a/b"]


@pytest.mark.asyncio
async def test_existing_dir_ok():
    client = _client("dir")
    client.mkdir.side_effect = PathExistsError("exists")
    await async_ensure_folder(client, "app:/home")
    client.get_meta.assert_awaited_once_with("app:/home")


@pytest.mark.asyncio
async def test_file_in_the_way():
    client = _client("file")
    client.mkdir.side_effect = PathExistsError("exists")
    with pytest.raises(FolderIsFileError) as exc:
        await async_ensure_folder(client, "app:/a")
    assert exc.value.path == "app:/a"


@pytest.mark.asyncio
async def test_unauthorized_propagates():
    client = _client()
    client.mkdir.side_effect = UnauthorizedError("bad")
    with pytest.raises(UnauthorizedError):
        await async_ensure_folder(client, "app:/home")


@pytest.mark.asyncio
async def test_app_root_never_created():
    client = _client()
    await async_ensure_folder(client, "app:/home")
    client.mkdir.assert_awaited_once_with("app:/home")
