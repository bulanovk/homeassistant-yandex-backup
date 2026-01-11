"""Pytest fixtures for Yandex Disk backup integration tests."""

# First, ensure the installed yadisk library is loaded before any local modules
# This prevents Python from treating tests/custom_components/yandex_disk_backup/ as a package
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

# Windows-specific fix for pytest-socket compatibility
# Use SelectorEventLoopPolicy on Windows to avoid ProactorEventLoop socket issues
if sys.platform == "win32":
    from asyncio import WindowsSelectorEventLoopPolicy
    asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())


# Pytest hook to ensure WindowsSelectorEventLoopPolicy is set before event_loop fixture
def pytest_configure(config):
    """Configure pytest to use WindowsSelectorEventLoopPolicy on Windows."""
    if sys.platform == "win32":
        from asyncio import WindowsSelectorEventLoopPolicy
        asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())

# Remove test directory from sys.path to prevent namespace conflicts
test_dir = Path(__file__).parent
sys.path = [p for p in sys.path if str(test_dir) not in p and str(test_dir.parent) not in p]

# Now load the installed yadisk first
import yadisk

# Now we can safely load our local custom_components.yandex_disk_backup modules
import importlib.util

project_root = Path(__file__).parent.parent.parent.parent

# We need to create the parent module first for relative imports to work
if "custom_components.yandex_disk_backup" not in sys.modules:
    # Create a parent module
    parent_module = type(sys)("custom_components.yandex_disk_backup")
    sys.modules["custom_components.yandex_disk_backup"] = parent_module

# Load const.py first (no dependencies)
const_path = project_root / "custom_components" / "yandex_disk_backup" / "const.py"
if const_path.exists() and "custom_components.yandex_disk_backup.const" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "custom_components.yandex_disk_backup.const", const_path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["custom_components.yandex_disk_backup.const"] = module
    spec.loader.exec_module(module)
    # Also set it as an attribute of the parent module
    setattr(sys.modules["custom_components.yandex_disk_backup"], "const", module)

# Load backup.py (depends on const)
backup_path = project_root / "custom_components" / "yandex_disk_backup" / "backup.py"
if backup_path.exists() and "custom_components.yandex_disk_backup.backup" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "custom_components.yandex_disk_backup.backup", backup_path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["custom_components.yandex_disk_backup.backup"] = module
    spec.loader.exec_module(module)
    # Also set it as an attribute of the parent module
    setattr(sys.modules["custom_components.yandex_disk_backup"], "backup", module)

# Load config_flow.py (depends on const)
config_flow_path = project_root / "custom_components" / "yandex_disk_backup" / "config_flow.py"
if config_flow_path.exists() and "custom_components.yandex_disk_backup.config_flow" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "custom_components.yandex_disk_backup.config_flow", config_flow_path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["custom_components.yandex_disk_backup.config_flow"] = module
    spec.loader.exec_module(module)
    # Also set it as an attribute of the parent module
    setattr(sys.modules["custom_components.yandex_disk_backup"], "config_flow", module)

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import EntityRegistry

from custom_components.yandex_disk_backup.backup import YandexDiskBackupAgent
from custom_components.yandex_disk_backup.const import (
    CONF_BACKUP_FOLDER,
    CONF_TOKEN,
    DEFAULT_BACKUP_FOLDER,
)


@pytest.fixture
def hass():
    """Create a mock Home Assistant instance."""
    mock_hass = Mock(spec=HomeAssistant)
    mock_hass.data = {}
    mock_hass.config = Mock()
    mock_hass.config.path = Mock(return_value="/tmp/homeassistant")
    
    # Mock bus and event system
    mock_hass.bus = Mock()
    mock_hass.bus.async_listen_once = AsyncMock(return_value=Mock())
    
    # Mock config_entries with proper flow manager methods
    mock_hass.config_entries = Mock()
    mock_hass.config_entries.async_add = AsyncMock()
    mock_hass.config_entries.entries = []
    mock_hass.config_entries.flow = Mock()
    mock_hass.config_entries.flow.async_init = AsyncMock(return_value={"type": "form", "flow_id": "test_flow", "step_id": "user"})
    mock_hass.config_entries.flow.async_configure = AsyncMock(return_value={"type": "create_entry", "flow_id": "test_flow", "title": "Yandex Disk", "data": {"token": "valid_token_abc123", "backup_folder": "/backups"}})
    mock_hass.config_entries.flow.async_progress_by_handler = Mock(return_value=[])
    mock_hass.config_entries.flow.async_progress = Mock(return_value=[])
    mock_hass.config_entries.async_unique_id = Mock()

    # Mock the async_add_executor_job method
    async def mock_add_executor_job(func, *args):
        return func(*args)

    mock_hass.async_add_executor_job = mock_add_executor_job
    return mock_hass


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    return Mock(
        spec=ConfigEntry,
        entry_id="test_entry_id",
        domain="yandex_disk_backup",
        unique_id="yandex_disk_test_unique_id",
        data={
            CONF_TOKEN: "test_token_abc123",
            CONF_BACKUP_FOLDER: DEFAULT_BACKUP_FOLDER,
        },
        title="Yandex Disk",
    )


@pytest.fixture
def mock_yadisk_client():
    """Create a mock yadisk AsyncClient."""
    client = AsyncMock()

    # Setup default disk info mock
    disk_info = Mock()
    disk_info.total_space = 10 * 1024**3  # 10 GB
    disk_info.used_space = 2 * 1024**3     # 2 GB (free_space calculated: 8 GB)

    async def get_disk_info_impl():
        return disk_info

    client.get_disk_info = AsyncMock(side_effect=get_disk_info_impl)

    # Setup default metadata mock
    meta = Mock()
    meta.name = "backup.tar"
    meta.size = 1024 * 1024  # 1 MB
    meta.created = datetime.now()
    meta.type = "file"

    async def get_meta_impl(path):
        return meta

    client.get_meta = AsyncMock(side_effect=get_meta_impl)

    # Setup default listdir mock - returns async generator
    list_item = Mock()
    list_item.name = "backup.tar"
    list_item.type = "file"
    list_item.created = datetime.now()

    async def listdir_impl(path):
        yield list_item

    client.listdir = listdir_impl

    # Setup download link mock
    async def get_download_link_impl(path):
        return "https://disk.yandex.ru/download/abc123"

    client.get_download_link = AsyncMock(side_effect=get_download_link_impl)

    # Setup other methods
    client.upload = AsyncMock()
    client.get_upload_link = AsyncMock(return_value="https://cloud-api.yandex.net/v1/disk/resources/upload?url=abc123")
    client.remove = AsyncMock()
    client.mkdir = AsyncMock()

    return client


@pytest.fixture(autouse=True)
def mock_http_session():
    """Automatically mock HTTP session for all tests."""
    # Create a mock HTTP response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.raise_for_status = Mock()

    # Create async chunk iterator
    async def chunk_iterator(size=1024):
        yield b"test_data"

    mock_response.content = AsyncMock()
    mock_response.content.iter_chunked = Mock(return_value=chunk_iterator())
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock()

    # Create mock session
    mock_session = AsyncMock()
    mock_session.get = Mock(return_value=mock_response)
    mock_session.put = Mock(return_value=mock_response)

    # Mock async_get_clientsession to return our mock session
    with patch("custom_components.yandex_disk_backup.backup.async_get_clientsession", return_value=mock_session):
        yield mock_session


@pytest.fixture
def backup_agent(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
    mock_yadisk_client: AsyncMock,
):
    """Create a YandexDiskBackupAgent fixture."""
    with patch(
        "custom_components.yandex_disk_backup.backup.AsyncClient",
        return_value=mock_yadisk_client,
    ):
        agent = YandexDiskBackupAgent(
            hass, mock_config_entry.data, mock_config_entry.unique_id
        )
        yield agent
        # Cleanup
        if agent._client:
            import asyncio
            asyncio.run(agent.async_close())
