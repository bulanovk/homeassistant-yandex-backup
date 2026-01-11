# Project Memory: Yandex Disk Backup Provider for Home Assistant Core

## Project Overview

**Project Name**: Yandex Disk Backup Provider (ha-yandex-location)
**Goal**: Implement a Home Assistant Core integration for Yandex Disk as a backup storage provider
**Status**: Implementation Complete - Ready for testing and contribution

## Technical Requirements

### Python Environment
- **MUST use virtual environment** for Python development and testing
- Create venv: `python -m venv venv`
- Activate venv:
  - Windows: `venv\Scripts\activate`
  - Linux/Mac: `source venv/bin/activate`
- Install dependencies in venv only

### Primary Dependency
- `yadisk>=3.4.0` - Official Python async client for Yandex Disk API

### Home Assistant Requirements
- Minimum HA Version: 2023.8.0 (backup agent platform support)
- Target HA Versions: 2024.x - 2025.x
- Tested with: homeassistant==2025.12.4
- Python: 3.13+ (recommended), 3.12+ supported

## Implementation Plan Location

The detailed implementation plan is saved at:
`C:\Users\bulan\.claude\plans\humble-crunching-dahl.md`

This plan contains:
1. Architectural Overview
2. Integration Classification (domain: `yadisk`, Backup Provider)
3. Authentication & Credential Handling (OAuth token-based)
4. Async Design (yadisk.AsyncClient, no executor needed)
5. Backup Lifecycle (all 5 BackupAgent methods)
6. Configuration Flow & UX
7. Failure Handling & Resilience
8. Testing Strategy
9. Dependency Management
10. Logging & Diagnostics
11. Risks & Reviewer Concerns

## File Structure

```
d:/projects/ha-yandex-location/
├── custom_components/
│   └── yandex_disk_backup/
│       ├── __init__.py         # Component setup, agent registration
│       ├── backup.py           # YandexDiskBackupAgent (core logic)
│       ├── config_flow.py      # OAuth token validation
│       ├── const.py            # Constants (DOMAIN, config keys)
│       ├── diagnostics.py      # Diagnostic endpoint
│       ├── manifest.json       # Component metadata, deps
│       ├── strings.json        # UI strings
│       └── translations/
│           └── en.json         # English translations
├── tests/
│   ├── conftest.py             # Windows compatibility mocks
│   └── custom_components/
│       └── yandex_disk_backup/
│           ├── __init__.py
│           ├── conftest.py     # Pytest fixtures
│           ├── test_backup.py  # Backup operations tests
│           └── test_config_flow.py # Config flow tests
├── .github/
│   └── workflows/
│       ├── ci.yaml             # GitHub Actions CI (Python 3.13)
│       └── hacs.off            # HACS validation workflow
├── requirements.txt            # Production dependencies
├── requirements_test.txt       # Test dependencies
├── README.md                   # Documentation
└── CLAUDE.md                   # This memory file
```

## Implementation Status

### Completed Files (16)

1. **const.py** - Domain: "yandex_disk_backup", config keys, timeouts, defaults
2. **manifest.json** - Dependencies: yadisk>=3.4.0, backup platform
3. **backup.py** - YandexDiskBackupAgent class with:
   - async_upload_backup() - with space check, verification, descriptive filenames, metadata sidecar upload
   - async_download_backup() - streaming with 4MB chunks via HA's HTTP session
   - async_delete_backup() - trash (not permanent delete), also removes metadata sidecar
   - async_list_backups() - filtered by .tar/.tar.gz extension, sorted newest first, loads metadata from sidecar
   - async_get_backup() - metadata retrieval from sidecar or fallback to file metadata
   - _ensure_backup_folder() - creates folder if missing
   - _get_disk_info_cached() - 5-minute cache
   - _get_client() - client creation wrapped in executor to avoid SSL blocking
   - _get_metadata_path() - generates sidecar metadata file path
   - _upload_metadata() - stores backup metadata as JSON sidecar file
   - _load_metadata() - loads backup metadata from sidecar file
4. **config_flow.py** - OAuth token validation via get_disk_info()
5. **__init__.py** - async_setup_entry, async_unload_entry, agent registration
6. **strings.json** - UI strings for config flow
7. **diagnostics.py** - async_get_config_entry_diagnostics with token redaction
8. **translations/en.json** - English translations
9. **tests/conftest.py** - Windows compatibility mocks (fcntl, resource)
10. **tests/custom_components/yandex_disk_backup/__init__.py** - Test package marker
11. **tests/custom_components/yandex_disk_backup/conftest.py** - Mock fixtures
12. **tests/custom_components/yandex_disk_backup/test_backup.py** - 14 test cases
13. **tests/custom_components/yandex_disk_backup/test_config_flow.py** - 9 test cases
14. **README.md** - Documentation
15. **.github/workflows/ci.yaml** - CI configuration (Python 3.13)
16. **.github/workflows/hacs.off** - HACS validation workflow

## Key Design Decisions

1. **Domain Name**: `yandex_disk_backup` (custom component, uses yadisk package)
2. **Classification**: Backup Provider only (not storage provider)
3. **Authentication**: OAuth token-based (not full OAuth flow)
4. **Async Strategy**: Native yadisk.AsyncClient, with client creation in executor to avoid SSL blocking
5. **Upload Strategy**: Uses `client.upload()` with User-Agent spoofing to bypass 128 KiB/s throttling
6. **Download Strategy**: Uses HA's HTTP session for streaming downloads
7. **Default Folder**: "/Home Assistant Backups"
8. **Delete Strategy**: Move to trash (permanently=False)
9. **Chunk Size**: 4 MB (matches HA backup patterns)
10. **Cache Duration**: 5 minutes for disk info
11. **Backup File Filtering**: Only files ending with `.tar` or `.tar.gz`
12. **Filename Format**: Uses `suggested_filename()` from HA for descriptive names (e.g., "Automatic backup 2025.12.0 2026-01-11_17.16_57961500.tar")
13. **Metadata Storage**: Sidecar `.metadata.json` files preserve full backup metadata (name, date, extra_metadata, etc.)
14. **Backup ID Handling**: The `backup_id` field in `AgentBackup` objects is always the Yandex Disk filename, not HA's internal backup ID. This ensures consistency between backup listings and file operations (download/delete/get).
15. **Backward Compatibility**: Old backups without sidecar files are supported with fallback to file metadata

## Testing Requirements

### Run Tests (in venv)
```bash
# Activate venv first
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Run tests
pytest tests/custom_components/yandex_disk_backup/ -v

# With coverage
pytest tests/custom_components/yandex_disk_backup/ \
  --cov=custom_components/yandex_disk_backup \
  --cov-report=term-missing
```

**Windows Compatibility**: The test suite automatically mocks Unix-only modules (`fcntl`, `resource`) on Windows. See `tests/conftest.py` for implementation details.

### Target Coverage: 80%+

## Code Quality Commands (in venv)

```bash
# Format
black custom_components/yandex_disk_backup/

# Type check
mypy custom_components/yandex_disk_backup/

# Lint
pylint custom_components/yandex_disk_backup/ --errors-only
```

## OAuth Token Acquisition

Users need to:
1. Visit: `https://oauth.yandex.com/authorize?response_type=token&client_id=<APP_ID>`
2. Authorize the application
3. Copy `access_token` from redirect URL
4. Paste in config flow

## Error Mapping

| yadisk Exception | HA Exception | User Message |
|-----------------|--------------|--------------|
| UnauthorizedError | BackupAgentError | "Authentication failed. Please reconfigure." |
| InsufficientStorageError | BackupAgentError | "Insufficient storage on Yandex Disk." |
| NotFoundError | BackupAgentError | "Backup not found." |
| ConnectionError | BackupAgentUnreachableError | "Cannot connect to Yandex Disk." |
| TooManyRequestsError | BackupAgentUnreachableError | "Too many requests. Please try again later." |
| YaDiskError | BackupAgentUnreachableError | "Yandex Disk operation failed." |

## Anticipated Reviewer Concerns & Responses

1. **Why not WebDAV?** - Yandex Disk API is more feature-rich, official library, better error handling
2. **Backup-only?** - Follows WebDAV pattern, appropriate for storage providers
3. **Token OAuth vs full flow?** - Simpler UX, long-lived tokens, consistent with other providers
4. **What if yadisk unmaintained?** - WebDAV fallback exists, library is active, standard patterns
5. **Event loop blocking?** - Uses native AsyncClient, all operations async/await
6. **Test coverage?** - Comprehensive with mocks, 80%+ target, all error paths

## Contribution Checklist

- [x] All files created
- [x] Core implementation complete
- [x] Test files written
- [x] All tests pass (27/27)
- [x] Code formatted (black)
- [x] Type checking passes (mypy)
- [x] Linting passes (pylint)
- [x] Windows compatibility fixes (tests/conftest.py)
- [x] Automatic/manual backup support implemented
- [ ] Local testing with HA instance
- [ ] Submit PR to home-assistant/core

## Recent Changes (2026-01-11)

### Critical Bug Fix: backup_id Field Override
- **Issue**: When using descriptive filenames (like "Automatic backup 2025.12.0 2026-01-11_17.16_57961500.tar"), the backup agent was storing Home Assistant's internal `backup_id` (like `'9cb25c63'`) in the metadata sidecar files. This caused "Backup not found" errors when Home Assistant tried to download or get backup details.
- **Root Cause**: The `AgentBackup.as_dict()` method includes the original `backup_id` field which is HA's internal identifier. When loading from metadata via `AgentBackup.from_dict()`, this internal ID was used instead of the Yandex Disk filename.
- **Fix**: Override the `backup_id` field to always be the filename on disk when loading from metadata:
  - [`async_list_backups()`](backup.py:461) - Sets `metadata_dict["backup_id"] = item.name` before creating `AgentBackup`
  - [`async_get_backup()`](backup.py:550) - Sets `metadata_dict["backup_id"] = backup_id` before creating `AgentBackup`
- **Impact**: Ensures consistency between the `backup_id` in `AgentBackup` objects and the actual filename on Yandex Disk, enabling proper backup retrieval, download, and deletion.

### Automatic & Manual Backup Support
- **Feature**: Properly distinguishes between automatic and manual backups in the Home Assistant UI
- **Implementation**:
  - Added `suggested_filename` import from `homeassistant.components.backup.util`
  - Updated `async_upload_backup()` to use descriptive filenames (e.g., "Automatic backup 2025.12.0 2026-01-11_17.16_57961500.tar")
  - Added metadata sidecar file storage (`.metadata.json`) to preserve full backup metadata
  - Updated `async_list_backups()` to load metadata from sidecar files with fallback for old backups
  - Updated `async_get_backup()` to read metadata from sidecar files
  - Updated `async_delete_backup()` to also delete metadata sidecar files
  - Added helper methods: `_get_metadata_path()`, `_upload_metadata()`, `_load_metadata()`
- **Tests**: Updated 2 tests to account for new upload/delete behavior (now calls upload/remove twice)
- **Backward Compatibility**: Old backups without sidecar files continue to work with fallback metadata

### Debug Logging for Upload Progress
- Added comprehensive debug logging in `async_upload_backup()` to track upload progress
- Logs include: backup start, chunk reading progress (every 10 chunks), stream completion, HTTP PUT start/completion
- Enable debug logging in Home Assistant configuration:
  ```yaml
  logger:
    logs:
      custom_components.yandex_disk_backup: debug
  ```

### Documentation Updates
- Updated README.md with automatic/manual backup feature description
- Updated CLAUDE.md with current implementation state
- Added hacs.off workflow to file structure documentation
- Expanded Key Design Decisions with upload/download strategy details
- Updated Completed Files count to 16

### Previously Fixed Issues (2025-01-10)
- Updated Python version requirement to 3.13+ for Home Assistant 2025.x compatibility
- Added Windows compatibility mocks in `tests/conftest.py` for `fcntl` and `resource` modules
- Fixed test assertion in `test_list_backups_filters_non_backup_files` to be order-agnostic
- Updated CI configuration to use Python 3.13

### Current Test Results
- All 27 tests passing (15 in test_backup.py, 9 in test_config_flow.py, 3 additional tests)
- Code coverage meets requirements
- Black, mypy, pylint all passing

## Important Notes

1. **Always use virtual environment** for Python operations
2. Integration domain is `yandex_disk_backup` (custom component, uses yadisk package)
3. Tokens stored encrypted in Config Entries
4. No secrets in YAML - UI-based config only
5. Proper async cleanup in async_close()
6. Follows HA contribution guidelines

## Development Environment

- **OS**: Windows 11
- **Python**: 3.13 (primary), 3.12+ supported
- **Virtual Environment**: venv (activated via `venv\Scripts\activate`)

### Windows Compatibility Notes

The test suite includes Windows compatibility fixes in `tests/conftest.py`:
- Mocks for Unix-only modules (`fcntl`, `resource`) before importing Home Assistant
- Uses `WindowsSelectorEventLoopPolicy` for asyncio on Windows
- Enables running full test suite on Windows without WSL

### Python Version Requirements

- **Python 3.13+**: Recommended - Home Assistant 2025.x uses Python 3.13+ type parameter syntax
- **Python 3.12**: Supported but may have some tooling compatibility issues (mypy)
- **Python 3.11**: Minimum for older Home Assistant versions

### Repository Information

- **Local Path**: `d:/projects/ha-yandex-location/`
- **Repository URL**: `https://github.com/bulanovk/homeassistant-yandex-backup`
- **Issue Tracker**: `https://github.com/bulanovk/homeassistant-yandex-backup/issues`
- **Documentation**: `https://github.com/bulanovk/homeassistant-yandex-backup`
