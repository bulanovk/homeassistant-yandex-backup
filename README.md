# Yandex Disk Backup Provider for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=flat-square)](https://github.com/custom-components/hacs)
[![CI](https://github.com/bulanovk/homeassistant-yandex-backup/actions/workflows/ci.yaml/badge.svg)](https://github.com/bulanovk/homeassistant-yandex-backup/actions/workflows/ci.yaml)
[![Release](https://img.shields.io/github/v/release/bulanovk/homeassistant-yandex-backup?style=flat-square)](https://github.com/bulanovk/homeassistant-yandex-backup/releases)

A Home Assistant custom integration that provides Yandex Disk as a backup storage provider.

## Features

- **Secure OAuth Token Authentication**: Uses Yandex Disk OAuth tokens for secure access
- **Async-First Design**: Built with native async support for optimal performance
- **Storage Monitoring**: Pre-upload checks to ensure sufficient space
- **Streaming Downloads**: Efficient 4MB chunk streaming for large backup files
- **Trash Deletion**: Safe deletion that moves files to trash first
- **UI Configuration**: Easy setup through Home Assistant's UI
- **Diagnostics Support**: Built-in diagnostics for troubleshooting
- **Automatic & Manual Backup Support**: Properly distinguishes between scheduled automatic backups and manual backups in the UI
- **Descriptive Filenames**: Backups stored with human-readable names including "Automatic" or "Custom" prefix

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add: `https://github.com/bulanovk/homeassistant-yandex-backup`
6. Select "Integration" as the category
7. Click "Add"
8. Search for "Yandex Disk Backup" and install it
9. Restart Home Assistant
10. Follow the configuration steps below

### Manual Installation

1. Download the latest release
2. Copy the `custom_components/yandex_disk_backup` directory to your Home Assistant `custom_components` directory
3. Restart Home Assistant
4. Navigate to **Settings > Devices & Services > Add Integration**
5. Search for "Yandex Disk Backup"

## Configuration

### Getting Your OAuth Token

1. Visit the Yandex OAuth authorization page:
   ```
   https://oauth.yandex.com/authorize?response_type=token&client_id=<YOUR_APP_ID>
   ```
2. Authorize the application
3. Copy the `access_token` from the redirect URL
4. Paste it in the integration configuration form

### Configuration Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| OAuth Token | Yes | - | Your Yandex Disk OAuth token |
| Backup Folder | No | /Home Assistant Backups | Path to store backups on Yandex Disk |

## Usage

Once configured, the integration will automatically appear as a backup option in Home Assistant's backup system:

1. Navigate to **Settings > System > Backups**
2. Click **Create Backup** for manual backups, or configure automatic backup schedules
3. Select "Yandex Disk" as the backup location
4. The backup will be uploaded to your Yandex Disk

### Automatic vs Manual Backups

The integration properly distinguishes between automatic and manual backups:

- **Automatic backups**: Created by Home Assistant's scheduled backup feature, named with "Automatic backup {version}" prefix
- **Manual backups**: Created manually by users, named with "Custom backup {version}" prefix or your custom name

Both types are displayed correctly in the Home Assistant backup UI with their respective labels.

## Architecture

```
Home Assistant Core
    └── Backup Platform
        └── YandexDiskBackupAgent
            ├── yadisk.AsyncClient (API operations)
            ├── HA HTTP Session (upload/download streaming)
            └── Disk Info Cache (5-minute TTL)
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

- Python 3.13+ (recommended) or Python 3.12+
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

# Type checking (may require Python 3.12 on Windows due to compatibility issues)
mypy custom_components/yandex_disk_backup/

# Linting
pylint custom_components/yandex_disk_backup/ --errors-only
```

## Dependencies

- `yadisk>=3.4.0` - Official Python client for Yandex Disk API

## Contributing

Contributions are welcome! This integration follows Home Assistant custom component best practices:
- Async-first design
- Config Entry based configuration
- Comprehensive error handling
- Full test coverage
- Proper logging and diagnostics

Please submit pull requests to the GitHub repository.

## License

MIT License - See LICENSE file for details

## Troubleshooting

### Debug Logging

To enable debug logging for troubleshooting upload/download issues, add the following to your Home Assistant `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.yandex_disk_backup: debug
```

After modifying the configuration, restart Home Assistant. The debug logs will show:
- Upload start with expected file size
- Chunk reading progress (every 10 chunks)
- Stream reading completion
- HTTP PUT upload progress
- Upload completion

View logs in **Settings > System > Logs** or via the Supervisor.

### Common Issues

**Insufficient Storage**: Ensure your Yandex Disk has enough free space before creating backups.

**Authentication Failed**: Re-enter your OAuth token in the integration configuration.

**Connection Timeout**: Check your network connection and Yandex Disk service status.

## Support

For issues and feature requests, please use the GitHub issue tracker:
https://github.com/bulanovk/homeassistant-yandex-backup/issues
