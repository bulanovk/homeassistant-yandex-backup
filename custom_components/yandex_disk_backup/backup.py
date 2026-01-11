"""Yandex Disk backup agent for Home Assistant."""

import asyncio
import json
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any, AsyncIterator


from yadisk import AsyncClient
from yadisk.exceptions import (
    InsufficientStorageError,
    NotFoundError,
    TooManyRequestsError,
    YaDiskConnectionError,
    YaDiskError,
)

from homeassistant.components.backup import AgentBackup, BackupAgent  # type: ignore[attr-defined]
from homeassistant.components.backup.agent import (  # type: ignore[import-not-found]
    BackupAgentError,
    BackupAgentUnreachableError,
)
from homeassistant.components.backup.util import (  # type: ignore[import-not-found] # pylint: disable=line-too-long
    suggested_filename,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import (
    CHUNK_SIZE,
    CONF_BACKUP_FOLDER,
    CONF_TOKEN,
    DATA_BACKUP_AGENT_LISTENERS,
    DEFAULT_BACKUP_FOLDER,
    DOMAIN,
    _LOGGER,
)


async def async_get_backup_agents(
    hass: HomeAssistant,
) -> list[BackupAgent]:
    """Return a list of backup agents.

    Args:
        hass: Home Assistant instance

    Returns:
        List of YandexDiskBackupAgent instances
    """
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    return [
        YandexDiskBackupAgent(hass, entry.runtime_data, entry.unique_id or "")
        for entry in entries
    ]


@callback
def async_register_backup_agents_listener(  # pylint: disable=unused-argument
    hass: HomeAssistant,
    *,
    listener: Callable[[], None],
    **kwargs: Any,
) -> Callable[[], None]:
    """Register a listener to be called when agents are added or removed.

    Args:
        hass: Home Assistant instance
        listener: Callback function to register
        **kwargs: Additional arguments

    Returns:
        Unsubscribe function
    """
    hass.data.setdefault(DATA_BACKUP_AGENT_LISTENERS, []).append(listener)

    @callback
    def remove_listener() -> None:
        """Remove the listener."""
        hass.data[DATA_BACKUP_AGENT_LISTENERS].remove(listener)
        if not hass.data[DATA_BACKUP_AGENT_LISTENERS]:
            del hass.data[DATA_BACKUP_AGENT_LISTENERS]

    return remove_listener


class YandexDiskBackupAgent(BackupAgent):
    """Yandex Disk backup agent for Home Assistant."""

    domain = "yandex_disk_backup"
    name = "Yandex Disk"

    def __init__(
        self,
        hass: HomeAssistant,
        config: ConfigType,
        unique_id: str,
    ) -> None:
        """Initialize the Yandex Disk backup agent.

        Args:
            hass: Home Assistant instance
            config: Configuration dict containing token and backup_folder
            unique_id: Unique ID for this agent instance
        """
        self.hass = hass
        self._config = config
        self.unique_id = unique_id
        self._client: AsyncClient | None = None
        self._backup_folder = config.get(CONF_BACKUP_FOLDER, DEFAULT_BACKUP_FOLDER)
        self._disk_info_cache: tuple[dict[str, Any], datetime] | None = None
        self._cache_lock = asyncio.Lock()

    async def _get_client(self) -> AsyncClient:
        """Get or create yadisk async client.

        Returns:
            AsyncClient instance configured with OAuth token
        """
        if self._client is None:

            def _create_client() -> AsyncClient:
                """Create AsyncClient - may block on SSL context initialization.

                Returns:
                    The created AsyncClient instance
                """
                return AsyncClient(token=self._config[CONF_TOKEN])

            # Run client creation in executor to avoid blocking SSL calls
            self._client = await self.hass.async_add_executor_job(_create_client)
        return self._client

    async def async_download_backup(  # type: ignore[override,misc]
        self,
        backup_id: str,
        **kwargs: Any,
    ) -> AsyncIterator[bytes]:
        """Download a backup from Yandex Disk.

        Args:
            backup_id: The backup ID (filename on Yandex Disk)
            **kwargs: Additional parameters

        Returns:
            Async iterator yielding bytes of the backup file in chunks

        Raises:
            BackupAgentError: If download fails
            BackupAgentUnreachableError: If Yandex Disk is unreachable
        """
        try:
            remote_path = f"{self._backup_folder}/{backup_id}"
            client = await self._get_client()
            download_url = await client.get_download_link(remote_path)
            # Return the async generator directly (don't yield from this function)
            return self._download_stream(download_url, backup_id)
        except NotFoundError as err:
            _LOGGER.error("Backup not found: %s", backup_id)
            raise BackupAgentError(f"Backup {backup_id} not found") from err
        except YaDiskConnectionError as err:
            _LOGGER.error("Connection error during download: %s", err)
            raise BackupAgentUnreachableError("Cannot connect to Yandex Disk") from err
        except TooManyRequestsError as err:
            _LOGGER.error("Rate limited during download: %s", err)
            raise BackupAgentUnreachableError(
                "Too many requests. Please try again later"
            ) from err
        except YaDiskError as err:
            _LOGGER.error("Download failed: %s", err)
            raise BackupAgentUnreachableError(str(err)) from err

    async def _download_stream(
        self,
        download_url: str,
        backup_id: str,
    ) -> AsyncIterator[bytes]:
        """Async generator that streams the backup download.

        Args:
            download_url: The URL to download from
            backup_id: The backup ID for logging

        Yields:
            Bytes of the backup file in chunks

        Raises:
            BackupAgentError: If download fails
            BackupAgentUnreachableError: If Yandex Disk is unreachable
        """
        try:
            # Stream download using HA's HTTP session
            session = async_get_clientsession(self.hass)
            async with session.get(download_url) as response:
                response.raise_for_status()

                # Stream in chunks (4 MB chunks per HA backup standard)
                async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                    yield chunk

            _LOGGER.info("Downloaded backup %s", backup_id)

        except NotFoundError as err:
            _LOGGER.error("Backup not found: %s", backup_id)
            raise BackupAgentError(f"Backup {backup_id} not found") from err
        except YaDiskConnectionError as err:
            _LOGGER.error("Connection error during download: %s", err)
            raise BackupAgentUnreachableError("Cannot connect to Yandex Disk") from err
        except TooManyRequestsError as err:
            _LOGGER.error("Rate limited during download: %s", err)
            raise BackupAgentUnreachableError(
                "Too many requests. Please try again later"
            ) from err
        except YaDiskError as err:
            _LOGGER.error("Download failed: %s", err)
            raise BackupAgentUnreachableError(str(err)) from err

    async def async_upload_backup(  # pylint: disable=too-many-locals
        self,
        *,
        open_stream,
        backup: AgentBackup,
        **kwargs: Any,
    ) -> None:
        """Upload a backup to Yandex Disk.

        Args:
            open_stream: Callable that returns async file stream
            backup: AgentBackup metadata
            **kwargs: Additional parameters

        Raises:
            BackupAgentError: If upload fails
            BackupAgentUnreachableError: If Yandex Disk is unreachable
        """
        # Use descriptive filename based on backup name and date
        # This preserves the "Automatic" or "Custom" prefix in the filename
        filename = suggested_filename(backup)
        remote_path = f"{self._backup_folder}/{filename}"

        try:
            # Get client once for reuse
            client = await self._get_client()

            # Ensure backup folder exists
            await self._ensure_backup_folder()

            # Check available space before upload
            disk_info = await self._get_disk_info_cached()
            if disk_info["free_space"] < backup.size:
                free_gb = disk_info["free_space"] / (1024**3)
                needed_gb = backup.size / (1024**3)
                raise BackupAgentError(
                    f"Insufficient storage: {free_gb:.2f} GB free, {needed_gb:.2f} GB needed"
                )

            # Use client.upload() with async generator for streaming
            # This provides:
            # - Automatic User-Agent spoofing to bypass 128 KiB/s throttling
            # - Built-in retry logic with exponential backoff
            # - Streaming without loading entire file into memory
            # See: https://yadisk.readthedocs.io/en/dev/known_issues.html
            _LOGGER.debug(
                "Starting upload for backup %s (expected size: %.2f MB)",
                backup.name,
                backup.size / (1024**2),
            )

            backup_file = await open_stream()

            async def stream_generator() -> AsyncIterator[bytes]:
                """Generator that yields chunks for streaming upload.

                Yields:
                    Chunks of backup data as they are read
                """
                total_bytes = 0
                chunk_count = 0
                async for chunk in backup_file:
                    total_bytes += len(chunk)
                    chunk_count += 1
                    if chunk_count % 10 == 0:
                        _LOGGER.debug(
                            "Upload progress: %.2f MB sent (%d chunks)",
                            total_bytes / (1024**2),
                            chunk_count,
                        )
                    yield chunk

                _LOGGER.debug(
                    "Finished reading stream: %.2f MB in %d chunks",
                    total_bytes / (1024**2),
                    chunk_count,
                )

            _LOGGER.debug("Starting client.upload() with throttling bypass")
            await client.upload(
                stream_generator,
                remote_path,
                overwrite=True,
                spoof_user_agent=True,  # Bypass 128 KiB/s throttling for .tar.gz
                # Use longer timeout for large files (connect, read)
                timeout=(30, 3600),
            )

            _LOGGER.debug("client.upload() completed successfully")

            # Upload metadata to sidecar file
            await self._upload_metadata(client, remote_path, backup)

            # Verify upload success
            try:
                meta = await client.get_meta(remote_path)
                if meta.size != backup.size:
                    _LOGGER.warning(
                        "Upload size mismatch: expected %d, got %d",
                        backup.size,
                        meta.size,
                    )
            except YaDiskError as err:
                _LOGGER.error("Upload verification failed: %s", err)

            _LOGGER.info(
                "Uploaded backup %s (%.2f MB)",
                backup.name,
                backup.size / (1024**2),
            )

        except InsufficientStorageError as err:
            _LOGGER.error("Yandex Disk storage full: %s", err)
            raise BackupAgentError("Insufficient storage on Yandex Disk") from err
        except YaDiskConnectionError as err:
            _LOGGER.error("Connection error during upload: %s", err)
            raise BackupAgentUnreachableError("Cannot connect to Yandex Disk") from err
        except TooManyRequestsError as err:
            _LOGGER.error("Rate limited during upload: %s", err)
            raise BackupAgentUnreachableError(
                "Too many requests. Please try again later"
            ) from err
        except YaDiskError as err:
            _LOGGER.error("Upload failed: %s", err)
            raise BackupAgentUnreachableError(str(err)) from err

    async def async_delete_backup(
        self,
        backup_id: str,
        **kwargs: Any,
    ) -> None:
        """Delete a backup from Yandex Disk.

        Args:
            backup_id: The backup ID to delete
            **kwargs: Additional parameters

        Raises:
            BackupAgentError: If deletion fails
            BackupAgentUnreachableError: If Yandex Disk is unreachable
        """
        remote_path = f"{self._backup_folder}/{backup_id}"
        metadata_path = self._get_metadata_path(remote_path)

        try:
            client = await self._get_client()
            # Move to trash first (safer than permanent delete)
            await client.remove(remote_path, permanently=False)
            _LOGGER.info("Deleted backup: %s", backup_id)
        except NotFoundError:
            # Already deleted - not an error
            _LOGGER.debug("Backup not found, may already be deleted: %s", backup_id)
        except YaDiskConnectionError as err:
            _LOGGER.error("Connection error during delete: %s", err)
            raise BackupAgentUnreachableError("Cannot connect to Yandex Disk") from err
        except YaDiskError as err:
            _LOGGER.error("Delete failed: %s", err)
            raise BackupAgentUnreachableError(str(err)) from err

        # Also try to delete the metadata sidecar file
        try:
            client = await self._get_client()
            await client.remove(metadata_path, permanently=False)
            _LOGGER.debug("Deleted metadata file: %s", metadata_path)
        except NotFoundError:
            # Metadata file doesn't exist - not an error
            _LOGGER.debug(
                "Metadata file not found (may not exist yet): %s", metadata_path
            )
        except YaDiskError as err:
            # Log warning but don't fail the delete operation
            _LOGGER.warning("Failed to delete metadata file: %s", err)

    async def async_list_backups(  # pylint: disable=too-many-locals
        self,
        **kwargs: Any,
    ) -> list[AgentBackup]:
        """List all backups on Yandex Disk.

        Args:
            **kwargs: Additional parameters

        Returns:
            List of AgentBackup objects

        Raises:
            BackupAgentError: If listing fails
            BackupAgentUnreachableError: If Yandex Disk is unreachable
        """
        try:
            backups = []
            client = await self._get_client()

            _LOGGER.debug("Listing backups in folder: %s", self._backup_folder)

            # listdir returns an async iterator
            item_count = 0
            filtered_count = 0
            async for item in client.listdir(self._backup_folder):  # type: ignore[attr-defined]
                item_count += 1
                _LOGGER.debug(
                    "Found item #%d: type=%r, name=%r, resource_id=%s",
                    item_count,
                    getattr(item, "type", "unknown"),
                    getattr(item, "name", None),
                    getattr(item, "resource_id", None),
                )

                # Check all filter conditions with detailed logging
                is_file = getattr(item, "type", None) == "file"
                name = getattr(item, "name", None)
                # Skip metadata files (they're processed with their backup files)
                is_metadata_file = name is not None and name.endswith(".metadata.json")
                is_backup = (
                    name is not None
                    and not is_metadata_file
                    and self._is_backup_file(name)
                )

                _LOGGER.debug(
                    "Filter check for %r: is_file=%s, name=%s, is_backup=%s",
                    name,
                    is_file,
                    name,
                    is_backup,
                )

                if is_file and name is not None and is_backup:
                    filtered_count += 1
                    _LOGGER.debug(
                        "Item %r passed filter, fetching metadata (%d/%d)",
                        name,
                        filtered_count,
                        item_count,
                    )

                    backup_path = f"{self._backup_folder}/{item.name}"

                    # Try to load metadata from sidecar file first
                    metadata_dict = await self._load_metadata(client, backup_path)

                    if metadata_dict:
                        # Use metadata from sidecar file
                        # IMPORTANT: Override backup_id to be the filename on disk
                        # The original backup_id in metadata is HA's internal ID which
                        # won't match our storage filename
                        metadata_dict["backup_id"] = item.name
                        backups.append(AgentBackup.from_dict(metadata_dict))
                        _LOGGER.debug(
                            "Loaded backup from metadata: %s (backup_id=%s)",
                            metadata_dict.get("name", item.name),
                            item.name,
                        )
                    else:
                        # Fallback to file metadata for old backups without sidecar
                        meta = await client.get_meta(backup_path)

                        # Convert datetime to ISO format string
                        date_str = (
                            meta.created.isoformat()
                            if isinstance(meta.created, datetime)
                            else str(meta.created)
                        )

                        # yadisk types can be None, but for files they should always be present
                        assert meta.size is not None
                        # Use item.name instead of meta.name for consistency
                        # Both item.name and meta.name can be None in yadisk types,
                        # but for files they should always have a name
                        assert item.name is not None
                        file_name = item.name if meta.name is None else meta.name
                        assert file_name is not None

                        backups.append(
                            AgentBackup(
                                backup_id=item.name,
                                name=file_name,
                                size=meta.size,
                                date=date_str,
                                addons=[],
                                database_included=False,
                                extra_metadata={},
                                folders=[],
                                homeassistant_included=True,
                                homeassistant_version=None,
                                protected=False,
                            )
                        )

            _LOGGER.debug(
                "List complete: %d total items, %d passed filter, %d backups added",
                item_count,
                filtered_count,
                len(backups),
            )

            # Sort by date, newest first
            backups.sort(key=lambda b: b.date, reverse=True)
            _LOGGER.debug("Listed %d backups", len(backups))
            return backups

        except NotFoundError:
            # Folder doesn't exist yet, create it
            _LOGGER.info("Backup folder not found, creating: %s", self._backup_folder)
            await self._ensure_backup_folder()
            return []
        except YaDiskConnectionError as err:
            _LOGGER.error("Connection error during list: %s", err)
            raise BackupAgentUnreachableError("Cannot connect to Yandex Disk") from err
        except YaDiskError as err:
            _LOGGER.error("List backups failed: %s", err)
            raise BackupAgentUnreachableError(str(err)) from err

    async def async_get_backup(
        self,
        backup_id: str,
        **kwargs: Any,
    ) -> AgentBackup:
        """Get backup metadata from Yandex Disk.

        Args:
            backup_id: The backup ID
            **kwargs: Additional parameters

        Returns:
            AgentBackup metadata

        Raises:
            BackupAgentError: If backup not found or get fails
            BackupAgentUnreachableError: If Yandex Disk is unreachable
        """
        remote_path = f"{self._backup_folder}/{backup_id}"

        try:
            client = await self._get_client()

            # Try to load metadata from sidecar file first
            metadata_dict = await self._load_metadata(client, remote_path)

            if metadata_dict:
                # Use metadata from sidecar file
                # IMPORTANT: Override backup_id to be the filename on disk (the backup_id parameter)
                # The original backup_id in metadata is HA's internal ID which
                # won't match our storage filename
                metadata_dict["backup_id"] = backup_id
                return AgentBackup.from_dict(metadata_dict)

            # Fallback to file metadata for old backups without sidecar
            meta = await client.get_meta(remote_path)

            # Convert datetime to ISO format string
            date_str = (
                meta.created.isoformat()
                if isinstance(meta.created, datetime)
                else str(meta.created)
            )

            # yadisk types can be None, but for files they should always be present
            assert meta.size is not None
            file_name = backup_id if meta.name is None else meta.name

            return AgentBackup(
                backup_id=backup_id,
                name=file_name,
                size=meta.size,
                date=date_str,
                addons=[],
                database_included=False,
                extra_metadata={},
                folders=[],
                homeassistant_included=True,
                homeassistant_version=None,
                protected=False,
            )

        except NotFoundError as err:
            raise BackupAgentError(f"Backup {backup_id} not found") from err
        except YaDiskConnectionError as err:
            _LOGGER.error("Connection error during get: %s", err)
            raise BackupAgentUnreachableError("Cannot connect to Yandex Disk") from err
        except YaDiskError as err:
            _LOGGER.error("Get backup failed: %s", err)
            raise BackupAgentUnreachableError(str(err)) from err

    @staticmethod
    def _get_metadata_path(backup_path: str) -> str:
        """Get the metadata file path for a backup.

        Args:
            backup_path: The path to the backup file

        Returns:
            The path to the metadata file
        """
        # Remove .tar extension if present and add .metadata.json
        if backup_path.endswith(".tar"):
            return backup_path[:-4] + ".metadata.json"
        return backup_path + ".metadata.json"

    async def _upload_metadata(
        self,
        client: AsyncClient,
        backup_path: str,
        backup: AgentBackup,
    ) -> None:
        """Upload backup metadata to a sidecar file.

        Args:
            client: The yadisk async client
            backup_path: The path to the backup file
            backup: The AgentBackup metadata
        """
        metadata_path = self._get_metadata_path(backup_path)
        metadata_dict = backup.as_dict()
        metadata_json = json.dumps(metadata_dict, ensure_ascii=False, indent=2)
        metadata_bytes = metadata_json.encode("utf-8")

        async def metadata_generator() -> AsyncIterator[bytes]:
            """Generator for metadata upload."""
            yield metadata_bytes

        await client.upload(
            metadata_generator,
            metadata_path,
            overwrite=True,
            timeout=30,
        )
        _LOGGER.debug("Uploaded metadata to %s", metadata_path)

    async def _load_metadata(
        self,
        client: AsyncClient,
        backup_path: str,
    ) -> dict[str, Any] | None:
        """Load backup metadata from sidecar file.

        Args:
            client: The yadisk async client
            backup_path: The path to the backup file

        Returns:
            The metadata dict, or None if not found
        """
        metadata_path = self._get_metadata_path(backup_path)
        try:
            download_url = await client.get_download_link(metadata_path)
            session = async_get_clientsession(self.hass)
            async with session.get(download_url) as response:
                response.raise_for_status()
                content = await response.text()
                return json.loads(content)
        except NotFoundError:
            _LOGGER.debug("No metadata file found at %s", metadata_path)
            return None
        except YaDiskError as err:
            _LOGGER.warning("Failed to load metadata from %s: %s", metadata_path, err)
            return None

    async def _ensure_backup_folder(self) -> None:
        """Ensure the backup folder exists on Yandex Disk.

        Raises:
            BackupAgentError: If folder creation fails
        """
        try:
            client = await self._get_client()
            await client.mkdir(self._backup_folder)
            _LOGGER.debug("Created backup folder: %s", self._backup_folder)
        except YaDiskError as err:
            # Folder might already exist, check if it's accessible
            try:
                client = await self._get_client()
                await client.get_meta(self._backup_folder)
            except YaDiskError:
                _LOGGER.error("Failed to create backup folder: %s", err)
                raise BackupAgentError("Cannot create backup folder") from err

    async def _get_disk_info_cached(self) -> dict[str, Any]:
        """Get disk info with caching to reduce API calls.

        Returns:
            Dict with total_space, used_space, free_space

        Raises:
            BackupAgentUnreachableError: If API call fails
        """
        async with self._cache_lock:
            # Cache for 5 minutes
            if self._disk_info_cache:
                cached_data, cache_time = self._disk_info_cache
                if (datetime.now() - cache_time).total_seconds() < 300:
                    return cached_data

            # Fetch fresh data
            try:
                client = await self._get_client()
                disk_info = await client.get_disk_info()
                # Handle potential None values from yadisk
                total_space = disk_info.total_space or 0
                used_space = disk_info.used_space or 0
                data = {
                    "total_space": total_space,
                    "used_space": used_space,
                    "free_space": total_space - used_space,
                }
                self._disk_info_cache = (data, datetime.now())
                return data
            except YaDiskConnectionError as err:
                _LOGGER.error("Connection error getting disk info: %s", err)
                raise BackupAgentUnreachableError(
                    "Cannot connect to Yandex Disk"
                ) from err
            except YaDiskError as err:
                _LOGGER.error("Failed to get disk info: %s", err)
                raise BackupAgentUnreachableError(str(err)) from err

    # Pattern for Home Assistant backup IDs (hexadecimal hash)
    # Home Assistant uses 8-64 character hexadecimal strings as backup IDs
    _BACKUP_ID_PATTERN = re.compile(r"^[a-f0-9]{8,64}$")

    @staticmethod
    def _is_backup_file(filename: str) -> bool:
        """Check if filename is a valid backup file.

        Args:
            filename: The filename to check

        Returns:
            True if filename is a backup file (ends with .tar/.tar.gz or is a hash-style ID)
        """
        # Check for traditional extensions
        if filename.endswith((".tar", ".tar.gz")):
            return True

        # Check for Home Assistant hash-style backup IDs (hexadecimal strings)
        # These are typically 8-64 characters long and consist of lowercase hex digits
        return bool(YandexDiskBackupAgent._BACKUP_ID_PATTERN.match(filename))

    async def async_close(self) -> None:
        """Close the yadisk client session.

        This should be called when unloading the integration.
        """
        if self._client is not None:
            await self._client.close()
            self._client = None
            _LOGGER.debug("Closed Yandex Disk client")
