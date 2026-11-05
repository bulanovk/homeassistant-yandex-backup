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

### Required OAuth Permissions

The current integration requires all three Yandex Disk permissions below:

| Permission | Scope | Purpose |
|------------|-------|---------|
| Access to Disk information | `cloud_api:disk.info` | Validate the token and check available storage before uploading |
| Read the entire Disk | `cloud_api:disk.read` | List backups, read metadata, and download archives |
| Write anywhere on Disk | `cloud_api:disk.write` | Create the backup folder, upload archives and metadata, and move deleted backups to trash |

**Access to the application folder (`cloud_api:disk.app_folder`) is not required and is not sufficient for the default configuration.** The integration uses a configurable regular folder on Yandex Disk (default: `/Home Assistant Backups`), rather than the special application folder (`app:/`). No Yandex ID profile or email permissions are needed.

> **Security:** Read and write permissions apply to the entire Disk. The backup folder setting controls where the integration operates, but does not restrict the token's permissions. Keep your token private and never include it in issues, logs, or screenshots. Consider using a separate Yandex account to isolate backups from personal files.

### Creating an OAuth Application

1. Sign in to the Yandex account whose Disk will store your backups.
2. Open the [Yandex OAuth application registration page](https://oauth.yandex.ru/client/new/).
3. If prompted to choose an application type, select **For API access or debugging**.
4. Enter an application name, such as `Home Assistant Backups`, and a contact email address.
5. Under data access, select the **three Yandex Disk permissions listed above**.
6. Create the application and copy its **ClientID**.

For this application type, Yandex uses `https://oauth.yandex.ru/verification_code` as the fixed redirect URI. You do not need to enter your Home Assistant URL.

### Getting Your OAuth Token

1. Open the following URL, replacing `YOUR_CLIENT_ID` with your application's ClientID:
   ```text
   https://oauth.yandex.ru/authorize?response_type=token&client_id=YOUR_CLIENT_ID
   ```
2. Make sure you are signed in to the account where you want to store backups, then approve the requested permissions.
3. Copy the token shown after authorization. If it appears in the redirect URL as `access_token=...`, copy only the parameter value, without `access_token=` or any subsequent parameters after `&`.

If you add permissions after obtaining a token, repeat authorization to obtain a token with the required permissions.

### Adding the Integration

After installing the integration and restarting Home Assistant:

1. Navigate to **Settings > Devices & Services > Add Integration**.
2. Search for **Yandex Disk Backup**.
3. Paste the token into **OAuth Token**, without an `OAuth ` prefix.
4. Leave **Backup Folder** set to `/Home Assistant Backups`, or specify another regular Disk folder. The integration creates the folder if needed; use the default path for the simplest initial setup.
5. Complete the configuration.

The integration accepts an existing token; it does not obtain one automatically. You do not need to enter a ClientID or Client secret in Home Assistant.

### Verifying Your Setup

1. Navigate to **Settings > System > Backups**.
2. Create a test backup and select **Yandex Disk** as the backup location.
3. Check that the archive and its accompanying `.metadata.json` file appear in the backup folder. Keep the metadata file alongside the archive; the integration uses it to identify and describe the backup.
4. Check that you can download the test backup through Home Assistant.

Successfully adding the integration only verifies access to Disk information; it does not verify all read and write operations. If listing or downloading backups fails, check `cloud_api:disk.read`. If creating the folder, uploading, or deleting backups fails, check `cloud_api:disk.write`, the folder path, and available storage. If token validation fails, check the token, `cloud_api:disk.info`, and network connectivity to Yandex, since connection errors can also appear as token validation errors.

For more information, see Yandex's documentation on [registering an application for API access](https://yandex.ru/dev/id/doc/ru/register-api) and [Disk API permissions and token acquisition](https://yandex.ru/dev/disk/api/concepts/quickstart.html).

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

## Uninstallation

Remove the configured integration instances **before** uninstalling its files. Removing the HACS download or the component directory alone does not remove Home Assistant's configuration entries.

1. Go to **Settings > System > Backups** and deselect **Yandex Disk** as a location for automatic backups. Select another location if you want automatic backups to continue elsewhere.
2. Go to **Settings > Devices & Services** and open **Yandex Disk Backup**.
3. Open the **three-dot menu next to the configured instance**, select **Delete**, and confirm. Repeat for any other configured instances. Use the instance menu, not the configuration wizard.
4. Uninstall the integration through HACS, or, for a manual installation, remove only the `yandex_disk_backup` directory inside your Home Assistant configuration directory's `custom_components` folder (usually `/config/custom_components/yandex_disk_backup`).
5. Restart Home Assistant and verify that Yandex Disk is no longer offered as a backup location.

Uninstalling the integration does **not** delete archives or `.metadata.json` files from Yandex Disk. If the OAuth token is no longer needed by any other application or Home Assistant instance, revoke its access in Yandex as well.

### If Files Were Already Removed

If the integration still appears or opening its setup wizard shows `Invalid handler specified`, its configuration entry may remain after the component files were removed:

1. Temporarily reinstall the component through HACS or restore its files manually.
2. Restart Home Assistant. **Do not add a new integration instance**; use the existing entry.
3. Follow the uninstallation steps above, deleting the configured instance before removing the files again.

Do not manually edit Home Assistant's `.storage` files as a first troubleshooting step.

If these steps do not help, report the following in an issue:

- Home Assistant Core version, integration version (before removal), and installation method (HACS or manual).
- The exact removal steps already performed and whether Home Assistant was restarted afterward.
- The step that fails, the full error message, and whether the instance menu offers **Delete**.
- Whether Yandex Disk remains under **Devices & Services**, in backup locations, or both.
- Relevant logs from **Settings > System > Logs**, including the traceback if available, and a screenshot of the remaining entry and its menu.

**Remove OAuth tokens and other sensitive information from logs and screenshots before sharing them.**

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
