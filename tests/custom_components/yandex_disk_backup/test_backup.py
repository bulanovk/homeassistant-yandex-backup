"""Tests for Yandex Disk backup agent."""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.components.backup import AgentBackup
from homeassistant.components.backup.agent import (
    BackupAgentError,
    BackupAgentUnreachableError,
)
from yadisk.exceptions import (
    InsufficientStorageError,
    NotFoundError,
    UnauthorizedError,
    YaDiskError,
)

from custom_components.yandex_disk_backup.const import (
    CONF_BACKUP_FOLDER,
    CONF_TOKEN,
    DEFAULT_BACKUP_FOLDER,
)


@pytest.mark.asyncio
async def test_upload_backup_success(backup_agent, mock_yadisk_client, mock_http_session):
    """Test successful backup upload using client.upload() with throttling bypass."""
    backup = AgentBackup(
        backup_id="core.2026-01-08.tar",
        name="core.2026-01-08.tar",
        size=1024 * 1024,  # 1 MB
        date=datetime.now().isoformat(),
        addons=[],
        database_included=False,
        extra_metadata={},
        folders=[],
        homeassistant_included=True,
        homeassistant_version="2024.1.0",
        protected=False,
    )

    # Create a mock stream (async iterator for upload)
    class MockStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    async def mock_open_stream():
        return MockStream()

    await backup_agent.async_upload_backup(
        open_stream=mock_open_stream,
        backup=backup,
    )

    # Verify client.upload() was called twice:
    # 1. For the backup file with throttling bypass enabled
    # 2. For the metadata sidecar file
    assert mock_yadisk_client.upload.call_count == 2

    # Check the first call (backup file) has throttling bypass enabled
    first_call_kwargs = mock_yadisk_client.upload.call_args_list[0].kwargs
    assert first_call_kwargs.get("spoof_user_agent") is True
    assert first_call_kwargs.get("overwrite") is True

    # Check the second call (metadata file) contains metadata.json in the path
    second_call_args = mock_yadisk_client.upload.call_args_list[1][0]
    second_call_kwargs = mock_yadisk_client.upload.call_args_list[1].kwargs
    assert ".metadata.json" in second_call_args[1]
    assert second_call_kwargs.get("overwrite") is True


@pytest.mark.asyncio
async def test_upload_backup_insufficient_storage(backup_agent, mock_yadisk_client):
    """Test upload with insufficient storage."""
    # Mock insufficient storage (10GB total - 9.5GB used = 0.5GB free, need 1GB)
    disk_info = Mock()
    disk_info.total_space = 10 * 1024**3
    disk_info.used_space = int(9.5 * 1024**3)  # Only 0.5GB free (calculated), less than 1GB backup size

    async def mock_get_disk_info():
        return disk_info

    mock_yadisk_client.get_disk_info.side_effect = mock_get_disk_info

    backup = AgentBackup(
        backup_id="large_backup.tar",
        name="large_backup.tar",
        size=1024**3,  # 1 GB needed
        date=datetime.now().isoformat(),
        addons=[],
        database_included=False,
        extra_metadata={},
        folders=[],
        homeassistant_included=True,
        homeassistant_version=None,
        protected=False,
    )

    # Create a mock stream (async iterator for upload)
    class MockStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    async def mock_open_stream():
        return MockStream()

    with pytest.raises(BackupAgentError, match="Insufficient storage"):
        await backup_agent.async_upload_backup(
            open_stream=mock_open_stream,
            backup=backup,
        )

    # client.upload() should not have been called due to insufficient storage
    mock_yadisk_client.upload.assert_not_called()


@pytest.mark.asyncio
async def test_download_backup_success(backup_agent, mock_yadisk_client, mock_http_session):
    """Test successful backup download."""
    backup_id = "core.2026-01-08.tar"

    # Create async iterator for chunks
    async def chunk_iterator():
        yield b"chunk1"
        yield b"chunk2"

    # Access the mock response through the session
    mock_response = mock_http_session.get.return_value
    mock_response.content.iter_chunked.return_value = chunk_iterator()

    # Download backup - need to await first since async_download_backup now returns the iterator
    stream = await backup_agent.async_download_backup(backup_id)
    chunks = []
    async for chunk in stream:
        chunks.append(chunk)

    assert len(chunks) == 2
    assert chunks == [b"chunk1", b"chunk2"]


@pytest.mark.asyncio
async def test_download_backup_not_found(backup_agent, mock_yadisk_client):
    """Test download with backup not found."""
    mock_yadisk_client.get_download_link.side_effect = NotFoundError("Not found")

    with pytest.raises(BackupAgentError, match="not found"):
        await backup_agent.async_download_backup("missing.tar")


@pytest.mark.asyncio
async def test_delete_backup_success(backup_agent, mock_yadisk_client):
    """Test successful backup deletion."""
    await backup_agent.async_delete_backup("old_backup.tar")

    # Verify remove was called twice:
    # 1. For the backup file
    # 2. For the metadata sidecar file
    assert mock_yadisk_client.remove.call_count == 2

    # Check the first call (backup file) uses permanently=False (trash)
    first_call_args = mock_yadisk_client.remove.call_args_list[0][0]
    first_call_kwargs = mock_yadisk_client.remove.call_args_list[0].kwargs
    assert first_call_args[0] == f"{DEFAULT_BACKUP_FOLDER}/old_backup.tar"
    assert first_call_kwargs.get("permanently") is False

    # Check the second call (metadata file) uses permanently=False (trash)
    second_call_args = mock_yadisk_client.remove.call_args_list[1][0]
    second_call_kwargs = mock_yadisk_client.remove.call_args_list[1].kwargs
    assert ".metadata.json" in second_call_args[0]
    assert second_call_kwargs.get("permanently") is False


@pytest.mark.asyncio
async def test_delete_backup_not_found(backup_agent, mock_yadisk_client):
    """Test delete with backup not found (idempotent)."""
    mock_yadisk_client.remove.side_effect = NotFoundError("Not found")

    # Should not raise an error
    await backup_agent.async_delete_backup("already_deleted.tar")


@pytest.mark.asyncio
async def test_list_backups_success(backup_agent, mock_yadisk_client):
    """Test successful backup listing."""
    backups = await backup_agent.async_list_backups()

    assert len(backups) == 1
    assert backups[0].backup_id == "backup.tar"
    assert backups[0].size == 1024 * 1024


@pytest.mark.asyncio
async def test_list_backups_filters_non_backup_files(backup_agent, mock_yadisk_client):
    """Test that listing filters out non-backup files."""
    # Mock listdir with mixed file types
    item1 = Mock()
    item1.name = "backup.tar"
    item1.type = "file"
    item1.created = datetime.now()

    item2 = Mock()
    item2.name = "readme.txt"
    item2.type = "file"
    item2.created = datetime.now()

    item3 = Mock()
    item3.name = "backup2.tar.gz"
    item3.type = "file"
    item3.created = datetime.now()

    item4 = Mock()
    item4.name = "folder"
    item4.type = "dir"
    item4.created = datetime.now()

    # Create async generator for listdir
    async def listdir_impl(path):
        yield item1
        yield item2
        yield item3
        yield item4

    mock_yadisk_client.listdir = listdir_impl

    # Mock get_meta for each backup file
    async def mock_get_meta(path):
        meta = Mock()
        meta.name = path.split("/")[-1]
        meta.size = 1024
        meta.created = datetime.now()
        return meta

    mock_yadisk_client.get_meta.side_effect = mock_get_meta

    backups = await backup_agent.async_list_backups()

    # Should only include .tar and .tar.gz files, not directories or .txt
    assert len(backups) == 2
    backup_ids = {b.backup_id for b in backups}
    assert backup_ids == {"backup.tar", "backup2.tar.gz"}


@pytest.mark.asyncio
async def test_list_backups_creates_folder_if_missing(backup_agent, mock_yadisk_client):
    """Test that listing creates folder if it doesn't exist."""
    # Create async generator that raises NotFoundError
    async def listdir_not_found(path):
        raise NotFoundError("Folder not found")
        yield  # Never reached, but needed for async generator

    mock_yadisk_client.listdir = listdir_not_found

    backups = await backup_agent.async_list_backups()

    assert len(backups) == 0
    # Should have attempted to create the folder
    mock_yadisk_client.mkdir.assert_called_once()


@pytest.mark.asyncio
async def test_get_backup_found(backup_agent, mock_yadisk_client):
    """Test getting backup that exists."""
    backup = await backup_agent.async_get_backup("backup.tar")

    assert backup is not None
    assert backup.backup_id == "backup.tar"
    assert backup.size == 1024 * 1024


@pytest.mark.asyncio
async def test_get_backup_not_found(backup_agent, mock_yadisk_client):
    """Test getting backup that doesn't exist."""
    mock_yadisk_client.get_meta.side_effect = NotFoundError("Not found")

    with pytest.raises(BackupAgentError, match="Backup missing.tar not found"):
        await backup_agent.async_get_backup("missing.tar")


@pytest.mark.asyncio
async def test_close_client(backup_agent, mock_yadisk_client):
    """Test closing the client."""
    await backup_agent.async_close()

    assert backup_agent._client is None


@pytest.mark.asyncio
async def test_disk_info_caching(backup_agent, mock_yadisk_client):
    """Test that disk info is cached."""
    # First call should fetch from API
    info1 = await backup_agent._get_disk_info_cached()
    assert info1["free_space"] == 8 * 1024**3

    # Second call should use cache
    info2 = await backup_agent._get_disk_info_cached()
    assert info2["free_space"] == 8 * 1024**3

    # Should only call get_disk_info once due to caching
    assert mock_yadisk_client.get_disk_info.call_count == 1


@pytest.mark.asyncio
async def test_yadisk_error_handling(backup_agent, mock_yadisk_client):
    """Test that yadisk errors are properly handled."""
    # Create async generator that raises YaDiskError
    async def listdir_error(path):
        raise YaDiskError("API Error")
        yield  # Never reached, but needed for async generator

    mock_yadisk_client.listdir = listdir_error

    with pytest.raises(BackupAgentUnreachableError):
        await backup_agent.async_list_backups()


def test_is_backup_file_with_extensions(backup_agent):
    """Test that _is_backup_file recognizes traditional extensions."""
    assert backup_agent._is_backup_file("backup.tar") is True
    assert backup_agent._is_backup_file("backup.tar.gz") is True
    assert backup_agent._is_backup_file("core.2024-01-01.tar") is True
    assert backup_agent._is_backup_file("core.2024-01-01.tar.gz") is True


def test_is_backup_file_with_hash_style_ids(backup_agent):
    """Test that _is_backup_file recognizes Home Assistant hash-style IDs."""
    # 8-character hex strings (common format)
    assert backup_agent._is_backup_file("51d5f41c") is True
    assert backup_agent._is_backup_file("d6a0ed36") is True
    assert backup_agent._is_backup_file("a1b2c3d4") is True

    # Longer hex strings (up to 64 characters)
    assert backup_agent._is_backup_file("a1b2c3d4e5f6") is True
    assert backup_agent._is_backup_file("a" * 64) is True


def test_is_backup_file_rejects_non_backup_files(backup_agent):
    """Test that _is_backup_file rejects non-backup files."""
    # Wrong extensions
    assert backup_agent._is_backup_file("readme.txt") is False
    assert backup_agent._is_backup_file("image.jpg") is False
    assert backup_agent._is_backup_file("document.pdf") is False

    # Too short for hash-style IDs
    assert backup_agent._is_backup_file("abc123") is False
    assert backup_agent._is_backup_file("a1b2") is False

    # Contains non-hex characters
    assert backup_agent._is_backup_file("g1h2i3j4") is False
    assert backup_agent._is_backup_file("51d5f41c.txt") is False

    # Empty string
    assert backup_agent._is_backup_file("") is False


@pytest.mark.asyncio
async def test_list_backups_includes_hash_style_ids(backup_agent, mock_yadisk_client):
    """Test that listing includes hash-style backup IDs."""
    # Mock listdir with hash-style backup files
    item1 = Mock()
    item1.name = "51d5f41c"
    item1.type = "file"
    item1.created = datetime.now()

    item2 = Mock()
    item2.name = "d6a0ed36"
    item2.type = "file"
    item2.created = datetime.now()

    item3 = Mock()
    item3.name = "readme.txt"
    item3.type = "file"
    item3.created = datetime.now()

    # Create async generator for listdir
    async def listdir_impl(path):
        yield item1
        yield item2
        yield item3

    mock_yadisk_client.listdir = listdir_impl

    # Mock get_meta for each backup file
    async def mock_get_meta(path):
        meta = Mock()
        meta.name = path.split("/")[-1]
        meta.size = 1024 * 1024
        meta.created = datetime.now()
        return meta

    mock_yadisk_client.get_meta.side_effect = mock_get_meta

    backups = await backup_agent.async_list_backups()

    # Should include hash-style IDs but not .txt files
    assert len(backups) == 2
    backup_ids = {b.backup_id for b in backups}
    assert backup_ids == {"51d5f41c", "d6a0ed36"}
