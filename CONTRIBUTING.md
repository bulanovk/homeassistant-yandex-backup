# Contributing

Contributions are welcome! Please submit pull requests to the GitHub repository.

This integration follows Home Assistant custom component best practices:
- Async-first design
- Config Entry based configuration
- Comprehensive error handling
- Full test coverage
- Proper logging and diagnostics

## Architecture

```
Home Assistant Core
    ├── Config flow: storage mode, PKCE sign-in or manual token, folder
    │   └── YandexOAuthClient (token refresh) → TokenManager (refreshes < 30 days before expiry, saves to the entry)
    └── Backup Platform
        └── YandexDiskBackupAgent
            ├── Access token from TokenManager (new yadisk.AsyncClient when it changes)
            ├── yadisk.AsyncClient (API operations)
            ├── HA HTTP Session (upload/download streaming)
            ├── Disk Info Cache (5-minute TTL)
            └── Storage path: app:/<instance folder> or the legacy backup folder
                └── Yandex Disk API
```

### Key Implementation Details

- **Upload**: Uses `client.upload()` with User-Agent spoofing to bypass 128 KiB/s throttling
- **Download**: Streams via HA's HTTP session in 4MB chunks
- **Client Creation**: Wrapped in executor to avoid SSL context blocking
- **Backup Filtering**: Only `.tar` and `.tar.gz` files are listed as backups
- **Metadata Storage**: Each backup has a corresponding `.metadata.json` sidecar file containing full backup metadata
- **Descriptive Filenames**: Backups use `suggested_filename()` format like "Automatic backup 2025.12.0 2026-01-11_17.16_57961500.tar"
- **Backward Compatibility**: Old backups without sidecar files are still supported with fallback metadata

## Development

### Requirements

- Python 3.14.2+ (required by Home Assistant 2026.3)
- Virtual environment required

### Running Tests

```bash
# Create and activate virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements_test.txt

# Run tests
pytest tests/custom_components/yandex_disk_backup/
```

**Note for Windows users**: Tests require Unix-only modules (`fcntl`, `resource`). The test suite includes mocks for these modules in `tests/conftest.py` to enable running tests on Windows.

### Code Quality

```bash
# Format code
black custom_components/yandex_disk_backup/

# Type checking
mypy custom_components/yandex_disk_backup/

# Linting
pylint custom_components/yandex_disk_backup/ --errors-only
```
