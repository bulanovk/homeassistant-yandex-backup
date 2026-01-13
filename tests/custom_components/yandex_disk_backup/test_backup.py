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

# Test constants
HA_BACKUP_ID = "abc123def456"  # HA's internal backup ID (UUID)
BACKUP_FILENAME = "core.2026-01-08.tar"  # Actual filename on Yandex Disk


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
    # Mock _resolve_filename to map HA backup_id to actual filename
    with patch.object(
        backup_agent, "_resolve_filename", return_value=BACKUP_FILENAME
    ):
        # Create async iterator for chunks
        async def chunk_iterator():
            yield b"chunk1"
            yield b"chunk2"

        # Access the mock response through the session
        mock_response = mock_http_session.get.return_value
        mock_response.content.iter_chunked.return_value = chunk_iterator()

        # Download backup using HA backup_id
        stream = await backup_agent.async_download_backup(HA_BACKUP_ID)
        chunks = []
        async for chunk in stream:
            chunks.append(chunk)

        assert len(chunks) == 2
        assert chunks == [b"chunk1", b"chunk2"]


@pytest.mark.asyncio
async def test_download_backup_not_found(backup_agent, mock_yadisk_client):
    """Test download with backup not found."""
    # Mock _resolve_filename to return None (backup not found)
    with patch.object(backup_agent, "_resolve_filename", return_value=None):
        with pytest.raises(BackupAgentError, match="not found"):
            await backup_agent.async_download_backup(HA_BACKUP_ID)


@pytest.mark.asyncio
async def test_delete_backup_success(backup_agent, mock_yadisk_client):
    """Test successful backup deletion."""
    filename = "old_backup.tar"
    # Mock _resolve_filename to map HA backup_id to actual filename
    with patch.object(backup_agent, "_resolve_filename", return_value=filename):
        await backup_agent.async_delete_backup(HA_BACKUP_ID)

        # Verify remove was called twice:
        # 1. For the backup file
        # 2. For the metadata sidecar file
        assert mock_yadisk_client.remove.call_count == 2

        # Check the first call (backup file) uses permanently=False (trash)
        first_call_args = mock_yadisk_client.remove.call_args_list[0][0]
        first_call_kwargs = mock_yadisk_client.remove.call_args_list[0].kwargs
        assert first_call_args[0] == f"{DEFAULT_BACKUP_FOLDER}/{filename}"
        assert first_call_kwargs.get("permanently") is False

        # Check the second call (metadata file) uses permanently=False (trash)
        second_call_args = mock_yadisk_client.remove.call_args_list[1][0]
        second_call_kwargs = mock_yadisk_client.remove.call_args_list[1].kwargs
        assert ".metadata.json" in second_call_args[0]
        assert second_call_kwargs.get("permanently") is False


@pytest.mark.asyncio
async def test_delete_backup_not_found(backup_agent, mock_yadisk_client):
    """Test delete with backup not found (raises error when filename not found)."""
    # Mock _resolve_filename to return None (backup not found)
    with patch.object(backup_agent, "_resolve_filename", return_value=None):
        with pytest.raises(BackupAgentError, match="not found"):
            await backup_agent.async_delete_backup(HA_BACKUP_ID)


@pytest.mark.asyncio
async def test_list_backups_success(backup_agent, mock_yadisk_client, mock_backup_metadata):
    """Test successful backup listing with HA backup_id from metadata."""
    # Mock _load_metadata to return HA backup_id
    with patch.object(
        backup_agent, "_load_metadata", return_value=mock_backup_metadata
    ):
        backups = await backup_agent.async_list_backups()

        assert len(backups) == 1
        assert backups[0].backup_id == HA_BACKUP_ID  # HA's internal backup ID
        assert backups[0].size == 1024 * 1024


@pytest.mark.asyncio
async def test_list_backups_filters_non_backup_files(backup_agent, mock_yadisk_client):
    """Test that listing filters out non-backup files."""
    # Mock _load_metadata to return None (fallback to file metadata)
    with patch.object(backup_agent, "_load_metadata", return_value=None):
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
async def test_get_backup_found(
    backup_agent, mock_yadisk_client, mock_backup_metadata
):
    """Test getting backup that exists."""
    filename = "backup.tar"
    # Mock _resolve_filename to map HA backup_id to actual filename
    # Mock _load_metadata to return HA backup_id
    with patch.object(backup_agent, "_resolve_filename", return_value=filename), patch.object(
        backup_agent, "_load_metadata", return_value=mock_backup_metadata
    ):
        backup = await backup_agent.async_get_backup(HA_BACKUP_ID)

        assert backup is not None
        assert backup.backup_id == HA_BACKUP_ID  # HA's internal backup ID
        assert backup.size == 1024 * 1024


@pytest.mark.asyncio
async def test_get_backup_not_found(backup_agent, mock_yadisk_client):
    """Test getting backup that doesn't exist."""
    # Mock _resolve_filename to return None (backup not found)
    with patch.object(backup_agent, "_resolve_filename", return_value=None):
        with pytest.raises(BackupAgentError, match=f"Backup {HA_BACKUP_ID} not found"):
            await backup_agent.async_get_backup(HA_BACKUP_ID)


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
    """Test that listing includes hash-style backup IDs (fallback without metadata)."""
    # Mock _load_metadata to return None (fallback to file metadata)
    with patch.object(backup_agent, "_load_metadata", return_value=None):
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


@pytest.mark.asyncio
async def test_resolve_filename_success(backup_agent, mock_yadisk_client, mock_backup_metadata):
    """Test successful filename resolution from HA backup_id."""
    # Mock listdir with a backup file
    list_item = Mock()
    list_item.name = BACKUP_FILENAME
    list_item.type = "file"
    list_item.created = datetime.now()

    async def listdir_impl(path):
        yield list_item

    mock_yadisk_client.listdir = listdir_impl

    # Mock _load_metadata to return HA backup_id
    with patch.object(
        backup_agent, "_load_metadata", return_value=mock_backup_metadata
    ):
        filename = await backup_agent._resolve_filename(HA_BACKUP_ID)
        assert filename == BACKUP_FILENAME


@pytest.mark.asyncio
async def test_resolve_filename_not_found(backup_agent, mock_yadisk_client):
    """Test filename resolution when backup not found."""
    # Mock empty listdir
    async def listdir_impl(path):
        return
        yield  # Never reached, but needed for async generator

    mock_yadisk_client.listdir = listdir_impl

    filename = await backup_agent._resolve_filename(HA_BACKUP_ID)
    assert filename is None


@pytest.mark.asyncio
async def test_upload_backup_unauthorized_error(backup_agent, mock_yadisk_client):
    """Test upload with unauthorized error."""
    from yadisk.exceptions import UnauthorizedError

    # The first upload call (backup file) raises UnauthorizedError
    # This should be caught and re-raised as BackupAgentUnreachableError
    mock_yadisk_client.upload.side_effect = UnauthorizedError("Invalid token")

    backup = AgentBackup(
        backup_id="core.2026-01-08.tar",
        name="core.2026-01-08.tar",
        size=1024,
        date=datetime.now().isoformat(),
        addons=[],
        database_included=False,
        extra_metadata={},
        folders=[],
        homeassistant_included=True,
        homeassistant_version="2024.1.0",
        protected=False,
    )

    class MockStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    async def mock_open_stream():
        return MockStream()

    with pytest.raises(BackupAgentUnreachableError):
        await backup_agent.async_upload_backup(
            open_stream=mock_open_stream,
            backup=backup,
        )


@pytest.mark.asyncio
async def test_upload_backup_connection_error(backup_agent, mock_yadisk_client):
    """Test upload with connection error."""
    from yadisk.exceptions import YaDiskConnectionError

    mock_yadisk_client.upload.side_effect = YaDiskConnectionError("Network error")

    backup = AgentBackup(
        backup_id="core.2026-01-08.tar",
        name="core.2026-01-08.tar",
        size=1024,
        date=datetime.now().isoformat(),
        addons=[],
        database_included=False,
        extra_metadata={},
        folders=[],
        homeassistant_included=True,
        homeassistant_version="2024.1.0",
        protected=False,
    )

    class MockStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    async def mock_open_stream():
        return MockStream()

    with pytest.raises(BackupAgentUnreachableError):
        await backup_agent.async_upload_backup(
            open_stream=mock_open_stream,
            backup=backup,
        )


@pytest.mark.asyncio
async def test_upload_backup_too_many_requests(backup_agent, mock_yadisk_client):
    """Test upload with rate limiting error."""
    from yadisk.exceptions import TooManyRequestsError

    mock_yadisk_client.upload.side_effect = TooManyRequestsError("Rate limited")

    backup = AgentBackup(
        backup_id="core.2026-01-08.tar",
        name="core.2026-01-08.tar",
        size=1024,
        date=datetime.now().isoformat(),
        addons=[],
        database_included=False,
        extra_metadata={},
        folders=[],
        homeassistant_included=True,
        homeassistant_version="2024.1.0",
        protected=False,
    )

    class MockStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    async def mock_open_stream():
        return MockStream()

    with pytest.raises(BackupAgentUnreachableError):
        await backup_agent.async_upload_backup(
            open_stream=mock_open_stream,
            backup=backup,
        )


@pytest.mark.asyncio
async def test_download_backup_connection_error(backup_agent, mock_yadisk_client):
    """Test download with connection error."""
    from yadisk.exceptions import YaDiskConnectionError

    with patch.object(
        backup_agent, "_resolve_filename", return_value=BACKUP_FILENAME
    ):
        mock_yadisk_client.get_download_link.side_effect = YaDiskConnectionError("Network error")

        with pytest.raises(BackupAgentUnreachableError):
            await backup_agent.async_download_backup(HA_BACKUP_ID)


@pytest.mark.asyncio
async def test_delete_backup_unauthorized_error(backup_agent, mock_yadisk_client):
    """Test delete with unauthorized error."""
    from yadisk.exceptions import UnauthorizedError

    mock_yadisk_client.remove.side_effect = UnauthorizedError("Invalid token")

    with patch.object(
        backup_agent, "_resolve_filename", return_value=BACKUP_FILENAME
    ):
        with pytest.raises(BackupAgentUnreachableError):
            await backup_agent.async_delete_backup(HA_BACKUP_ID)


@pytest.mark.asyncio
async def test_delete_backup_connection_error(backup_agent, mock_yadisk_client):
    """Test delete with connection error."""
    from yadisk.exceptions import YaDiskConnectionError

    mock_yadisk_client.remove.side_effect = YaDiskConnectionError("Network error")

    with patch.object(
        backup_agent, "_resolve_filename", return_value=BACKUP_FILENAME
    ):
        with pytest.raises(BackupAgentUnreachableError):
            await backup_agent.async_delete_backup(HA_BACKUP_ID)


@pytest.mark.asyncio
async def test_ensure_backup_folder_creates_folder(backup_agent, mock_yadisk_client):
    """Test that _ensure_backup_folder creates folder if it doesn't exist."""
    # Mock mkdir to succeed
    mock_yadisk_client.mkdir.return_value = None

    await backup_agent._ensure_backup_folder()

    mock_yadisk_client.mkdir.assert_called_once_with(backup_agent._backup_folder)


@pytest.mark.asyncio
async def test_ensure_backup_folder_already_exists(backup_agent, mock_yadisk_client):
    """Test that _ensure_backup_folder handles existing folder."""
    from yadisk.exceptions import YaDiskError

    # Mock mkdir to raise error (folder already exists)
    mock_yadisk_client.mkdir.side_effect = YaDiskError("Folder exists")
    # Mock get_meta to succeed (folder exists and is accessible)
    mock_yadisk_client.get_meta.return_value = Mock()

    await backup_agent._ensure_backup_folder()

    mock_yadisk_client.mkdir.assert_called_once()
    mock_yadisk_client.get_meta.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_backup_folder_creation_fails(backup_agent, mock_yadisk_client):
    """Test that _ensure_backup_folder raises error when creation fails."""
    from yadisk.exceptions import YaDiskError

    # Mock mkdir to raise error
    mock_yadisk_client.mkdir.side_effect = YaDiskError("Permission denied")
    # Mock get_meta to also raise error (folder not accessible)
    mock_yadisk_client.get_meta.side_effect = YaDiskError("Not found")

    with pytest.raises(BackupAgentError, match="Cannot create backup folder"):
        await backup_agent._ensure_backup_folder()


@pytest.mark.asyncio
async def test_upload_metadata_success(backup_agent, mock_yadisk_client):
    """Test successful metadata upload."""
    backup = AgentBackup(
        backup_id="test.tar",
        name="test.tar",
        size=1024,
        date=datetime.now().isoformat(),
        addons=[],
        database_included=False,
        extra_metadata={},
        folders=[],
        homeassistant_included=True,
        homeassistant_version="2024.1.0",
        protected=False,
    )

    await backup_agent._upload_metadata(mock_yadisk_client, "/folder/test.tar", backup)

    # Verify upload was called with metadata
    mock_yadisk_client.upload.assert_called()
    call_args = mock_yadisk_client.upload.call_args
    assert ".metadata.json" in call_args[0][1]


@pytest.mark.asyncio
async def test_load_metadata_success(backup_agent, mock_yadisk_client, mock_http_session):
    """Test successful metadata loading."""
    import json

    metadata = {
        "backup_id": "test_id",
        "name": "test.tar",
        "size": 1024,
    }

    mock_yadisk_client.get_download_link.return_value = "http://example.com/metadata.json"

    # Mock HTTP response
    mock_response = mock_http_session.get.return_value
    mock_response.text = AsyncMock(return_value=json.dumps(metadata))
    mock_response.raise_for_status = Mock()

    result = await backup_agent._load_metadata(mock_yadisk_client, "/folder/test.tar")

    assert result == metadata


@pytest.mark.asyncio
async def test_load_metadata_not_found(backup_agent, mock_yadisk_client):
    """Test metadata loading when file not found."""
    from yadisk.exceptions import NotFoundError

    mock_yadisk_client.get_download_link.side_effect = NotFoundError("Not found")

    result = await backup_agent._load_metadata(mock_yadisk_client, "/folder/test.tar")

    assert result is None


@pytest.mark.asyncio
async def test_load_metadata_api_error(backup_agent, mock_yadisk_client):
    """Test metadata loading with API error."""
    from yadisk.exceptions import YaDiskError

    mock_yadisk_client.get_download_link.side_effect = YaDiskError("API Error")

    result = await backup_agent._load_metadata(mock_yadisk_client, "/folder/test.tar")

    assert result is None


def test_get_metadata_path(backup_agent):
    """Test metadata path generation."""
    path = backup_agent._get_metadata_path("/folder/backup.tar")
    assert path == "/folder/backup.metadata.json"

    path = backup_agent._get_metadata_path("/folder/subfolder/backup.tar.gz")
    assert path == "/folder/subfolder/backup.tar.gz.metadata.json"


@pytest.mark.asyncio
async def test_get_backup_fallback_to_file_metadata(backup_agent, mock_yadisk_client):
    """Test getting backup falls back to file metadata when sidecar missing."""
    from datetime import datetime

    filename = "backup.tar"

    with patch.object(
        backup_agent, "_resolve_filename", return_value=filename
    ):
        # Mock _load_metadata to return None (no sidecar)
        with patch.object(backup_agent, "_load_metadata", return_value=None):
            # Mock get_meta for file metadata fallback
            file_meta = Mock()
            file_meta.name = filename
            file_meta.size = 1024 * 1024  # 1 MB - matches the fixture
            file_meta.created = datetime.now()

            mock_yadisk_client.get_meta.return_value = file_meta

            backup = await backup_agent.async_get_backup(HA_BACKUP_ID)

            assert backup is not None
            assert backup.backup_id == HA_BACKUP_ID
            assert backup.size == 1024 * 1024


@pytest.mark.asyncio
async def test_list_backups_fallback_to_file_metadata(backup_agent, mock_yadisk_client):
    """Test listing backups falls back to file metadata when sidecar missing."""
    from datetime import datetime

    # Mock _load_metadata to return None (no sidecar files)
    with patch.object(backup_agent, "_load_metadata", return_value=None):
        item = Mock()
        item.name = "backup.tar"
        item.type = "file"
        item.created = datetime.now()

        async def listdir_impl(path):
            yield item

        mock_yadisk_client.listdir = listdir_impl

        # Mock get_meta for file metadata fallback
        file_meta = Mock()
        file_meta.name = "backup.tar"
        file_meta.size = 1024 * 1024
        file_meta.created = datetime.now()

        mock_yadisk_client.get_meta.return_value = file_meta

        backups = await backup_agent.async_list_backups()

        assert len(backups) == 1
        assert backups[0].backup_id == "backup.tar"  # Falls back to filename
        assert backups[0].size == 1024 * 1024


@pytest.mark.asyncio
async def test_list_backups_skips_metadata_files(backup_agent, mock_yadisk_client):
    """Test that listing skips metadata sidecar files."""
    from datetime import datetime

    with patch.object(backup_agent, "_load_metadata", return_value=None):
        # Create mix of backup and metadata files
        item1 = Mock()
        item1.name = "backup.tar"
        item1.type = "file"
        item1.created = datetime.now()

        item2 = Mock()
        item2.name = "backup.tar.metadata.json"
        item2.type = "file"
        item2.created = datetime.now()

        async def listdir_impl(path):
            yield item1
            yield item2

        mock_yadisk_client.listdir = listdir_impl

        # Mock get_meta only for backup file (not called for metadata file)
        async def mock_get_meta(path):
            if ".metadata.json" in path:
                raise NotFoundError("Should not be called for metadata files")
            meta = Mock()
            meta.name = "backup.tar"
            meta.size = 1024
            meta.created = datetime.now()
            return meta

        mock_yadisk_client.get_meta.side_effect = mock_get_meta

        backups = await backup_agent.async_list_backups()

        # Should only include backup.tar, not the metadata sidecar
        assert len(backups) == 1
        assert backups[0].backup_id == "backup.tar"


@pytest.mark.asyncio
async def test_upload_backup_with_suggested_filename(backup_agent, mock_yadisk_client):
    """Test that upload uses descriptive suggested filename."""
    from datetime import datetime

    backup = AgentBackup(
        backup_id="abc123",
        name="Automatic backup 2025.12.0 2026-01-12_10.30",
        size=1024,
        date=datetime.now().isoformat(),
        addons=[],
        database_included=False,
        extra_metadata={},
        folders=[],
        homeassistant_included=True,
        homeassistant_version="2025.12.0",
        protected=False,
    )

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

    # Verify upload was called
    assert mock_yadisk_client.upload.call_count == 2

    # Check that the filename includes the suggested name
    first_call_args = mock_yadisk_client.upload.call_args_list[0][0]
    uploaded_path = first_call_args[1]
    # The filename should be based on the backup name
    assert "2025.12.0" in uploaded_path or "Automatic" in uploaded_path or "backup" in uploaded_path


@pytest.mark.asyncio
async def test_list_backups_with_metadata_file_only(backup_agent, mock_yadisk_client):
    """Test listing when only metadata file exists (backup already deleted)."""
    from datetime import datetime

    with patch.object(backup_agent, "_load_metadata", return_value=None):
        # Create only a metadata file (no backup file)
        item = Mock()
        item.name = "backup.tar.metadata.json"
        item.type = "file"
        item.created = datetime.now()

        async def listdir_impl(path):
            yield item

        mock_yadisk_client.listdir = listdir_impl

        backups = await backup_agent.async_list_backups()

        # Should skip metadata files and return empty list
        assert len(backups) == 0


@pytest.mark.asyncio
async def test_disk_info_cache_expiration(backup_agent, mock_yadisk_client):
    """Test that disk info cache expires after 5 minutes."""
    from datetime import datetime, timedelta

    # First call - should fetch from API
    info1 = await backup_agent._get_disk_info_cached()
    assert info1["free_space"] == 8 * 1024**3

    # Modify the cache time to simulate expiration
    old_time = datetime.now() - timedelta(seconds=301)  # More than 5 minutes ago
    if backup_agent._disk_info_cache:
        backup_agent._disk_info_cache = (backup_agent._disk_info_cache[0], old_time)

    # Second call should fetch from API again due to cache expiration
    info2 = await backup_agent._get_disk_info_cached()
    assert info2["free_space"] == 8 * 1024**3

    # Should have called get_disk_info twice (cache expired)
    assert mock_yadisk_client.get_disk_info.call_count == 2
