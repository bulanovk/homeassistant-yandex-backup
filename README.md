# Yandex Disk Backup Provider for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=flat-square)](https://github.com/custom-components/hacs)
[![CI](https://github.com/bulanovk/homeassistant-yandex-backup/actions/workflows/ci.yaml/badge.svg)](https://github.com/bulanovk/homeassistant-yandex-backup/actions/workflows/ci.yaml)
[![Release](https://img.shields.io/github/v/release/bulanovk/homeassistant-yandex-backup?style=flat-square)](https://github.com/bulanovk/homeassistant-yandex-backup/releases)

A Home Assistant custom integration that provides Yandex Disk as a backup storage provider.

## Features

- **Sign-in with Yandex**: App-folder storage signs in with the built-in Yandex application (PKCE) and reaches only its own folder; disk-folder storage uses a manual token
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

### Storage modes and permissions

Choose a storage mode when adding the integration. Each mode asks Yandex only for the permissions it needs:

| Storage mode | Where backups go | Scopes requested | Authorization |
|--------------|------------------|------------------|---------------|
| **App folder** (recommended) | `app:/<instance folder>` inside the application's own folder | `cloud_api:disk.app_folder`, `cloud_api:disk.info` | Sign in to Yandex |
| **Disk folder** (legacy) | A regular folder on your Disk, default `/Home Assistant Backups` | `cloud_api:disk.info`, `cloud_api:disk.read`, `cloud_api:disk.write` | Manual token with full disk access |

In app-folder mode the integration can only reach its own application folder. It cannot read or write your other files. Disk-folder mode grants access to the entire Disk; it stays available for existing setups and is considered legacy.

> **Security:** Keep tokens private and never include them in issues, logs, or screenshots. Consider a separate Yandex account for backups.

### Creating an OAuth application for disk-folder mode (legacy)

Disk-folder mode is legacy. Use app-folder mode for new setups. Only create an application if you must keep full disk access.

App-folder mode signs in with the built-in application, so you do not need to create one for it. Disk-folder (legacy) mode needs a token with full disk access, which the built-in application cannot grant, so create an application of your own and use its ClientID to obtain the token:

1. Sign in to the Yandex account whose Disk will store your backups.
2. Open the [Yandex OAuth application registration page](https://oauth.yandex.ru/client/new/).
3. Enter an application name, such as `Home Assistant Backups`, and a contact email address.
4. Under data access, select the scopes listed for disk-folder mode in the table above.
5. Create the application and copy its **ClientID**.

Yandex may ask for an application type and platform; choose the options that allow the token to be shown after authorization.

### Adding the Integration

After installing the integration and restarting Home Assistant:

1. Navigate to **Settings > Devices & Services > Add Integration**.
2. Search for **Yandex Disk Backup**.
3. Choose a **Storage mode**:
   - **App folder** (recommended): Home Assistant opens the Yandex sign-in page. Allow access and return to Home Assistant. This needs an external URL configured under **Settings > System > Network**.
   - **Disk folder** (legacy): paste a token with full disk access, see [Manual token](#manual-token).
4. For app-folder mode: enter an **instance folder** name, such as `home`. Use a different name for each Home Assistant instance. Backups are stored in `app:/<instance folder>`.
5. For disk-folder mode: leave **Backup folder** at `/Home Assistant Backups` or enter another path. The folder is created if needed.
6. Complete the configuration.

Signed-in tokens are stored in the config entry, refreshed before they expire, and you are asked to reauthenticate if Yandex revokes the authorization.

### Manual token

Disk-folder (legacy) storage needs a token with full disk access. Create it yourself:

1. Open the following URL, replacing `YOUR_CLIENT_ID` with your application's ClientID:
   ```text
   https://oauth.yandex.ru/authorize?response_type=token&client_id=YOUR_CLIENT_ID
   ```
2. Make sure you are signed in to the account where you want to store backups, then approve the requested permissions.
3. Copy the token shown after authorization. If it appears in the redirect URL as `access_token=...`, copy only the parameter value, without `access_token=` or any subsequent parameters after `&`.

Manually entered tokens are not refreshed automatically. When one expires, reauthenticate with a new token.

### Multiple Home Assistant instances

Several Home Assistant instances can use the same Yandex account. Give each instance its own **instance folder** (app-folder mode) so they write to separate folders. Folders organize backups but do not isolate access: any instance that holds the application's token can read the whole application folder. Use separate Yandex accounts if instances must not see each other's backups.

A step-by-step guide for moving an existing full-access setup into app-folder storage is not published yet. Until it is, changing the location in **Reconfigure** shows the old and new paths and moves nothing automatically.

### Changing the storage mode or folder

Open the integration's menu and choose **Reconfigure**. Choose the storage mode and folder as when adding the integration. You authorize again, and the stored token is replaced. If the backup location changes (a different mode or folder), the setup shows the old and new paths. Existing backups are **not** moved automatically: move the backup files (including their `.metadata.json` files) to the new folder yourself through the Yandex Disk web interface. Until you do, Home Assistant does not list them, because the entry only reads the new location.

### Verifying Your Setup

1. Navigate to **Settings > System > Backups**.
2. Create a test backup and select **Yandex Disk** as the backup location.
3. Check that the archive and its accompanying `.metadata.json` file appear in the backup folder. Keep the metadata file alongside the archive; the integration uses it to identify and describe the backup.
4. Check that you can download the test backup through Home Assistant.

If listing or downloading backups fails, check the scopes for your storage mode. If creating the folder, uploading, or deleting backups fails, check the folder path and available storage. If authorization fails, check the token (or the sign-in attempt), the external URL for sign-in, and network connectivity to Yandex.

For more information, see Yandex's documentation on [registering an application for API access](https://yandex.ru/dev/id/doc/ru/register-api) and [Disk API permissions](https://yandex.ru/dev/disk/api/concepts/quickstart.html).

### Configuration Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| Storage mode | Yes | App folder | App folder (recommended) or Disk folder (legacy, full disk access) |
| Token | Disk folder only | - | Token with full disk access from your own Yandex OAuth application |
| Instance folder | App folder only | - | Name of the folder under `app:/` for this instance |
| Backup folder | Disk folder only | /Home Assistant Backups | Path to store backups on Yandex Disk |

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

## Dependencies

- `yadisk>=3.4.0` - Official Python client for Yandex Disk API

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for architecture, development setup, tests, and code quality checks.

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

**Authentication Failed**: Reauthenticate the integration. App-folder entries sign in to Yandex again; disk-folder entries need a new manual token.

**Connection Timeout**: Check your network connection and Yandex Disk service status.

## Support

For issues and feature requests, please use the GitHub issue tracker:
https://github.com/bulanovk/homeassistant-yandex-backup/issues
