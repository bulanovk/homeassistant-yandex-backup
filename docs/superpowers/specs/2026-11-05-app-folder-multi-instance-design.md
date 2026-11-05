# Application-folder storage for multiple Home Assistant instances

Date: 2026-11-05
Status: Design only; API behavior requires live verification before release.
Selected approach: Option 1 — one OAuth application with a separate subfolder for each Home Assistant instance.

## Intent

Reduce the integration's access from the entire Yandex Disk to the OAuth application's folder while allowing multiple Home Assistant instances to store backups on the same Yandex account without mixing their backup lists or overwriting each other's files.

The user selected the shared-application/subfolder approach. Configuration details below are proposed engineering decisions, not additional user requirements. This document does not implement the feature.

## Goals

- Support application-relative paths such as `app:/home` and `app:/country-house`.
- Require `cloud_api:disk.app_folder` for file operations instead of full-Disk `cloud_api:disk.read` and `cloud_api:disk.write`.
- Retain `cloud_api:disk.info` for token validation and free-space checks.
- Keep all backup operations and metadata sidecars within the selected instance subfolder.
- Preserve existing ordinary-folder configurations and their behavior.

## Non-goals and security boundaries

- Subfolders are organizational separation, not authorization boundaries. A token with access to the application folder can potentially access other instance subfolders.
- Different tokens for the same OAuth application must not be presented as per-instance security isolation. Verify shared-folder behavior with real tokens before release.
- Separate OAuth applications per instance, separate Yandex accounts, and account-wide isolation are outside this design.
- Do not remove the Disk-information permission or the existing free-space check in this iteration.
- Do not automatically move, rename, or delete existing backups.
- Do not implement token acquisition, automatic token refresh, or central coordination between HA instances.

## Storage layout

All participating instances use the same OAuth application and Yandex account. Each instance is configured with a different subfolder:

```text
app:/
  home/
    <backup>.tar
    <backup>.metadata.json
  country-house/
    <backup>.tar
    <backup>.metadata.json
  testing/
    <backup>.tar
    <backup>.metadata.json
```

Yandex controls the physical application-folder location, typically under the user's Apps/Приложения directory. Never construct that physical path: use the `app:/` namespace. The application-folder root is created by Yandex upon access, according to its documentation.

Tokens grant access to the application folder, not to the configured subfolder alone. Shared quota, account availability, and access to sibling subfolders remain shared risks. Users must choose distinct subfolders; instances cannot discover or enforce uniqueness across independent HA installations. Two instances using the same subfolder will share a backup list and can overwrite identically named files or delete each other's backups.

## OAuth permissions

Application-folder mode requests:

- `cloud_api:disk.app_folder` — file management within the application folder.
- `cloud_api:disk.info` — account-level storage information, without full-Disk file access.

Do not request full-Disk read/write scopes for application-folder mode. Adding `disk.app_folder` to an already broadly authorized token does not restrict that token. Users must obtain a token without broad read/write permissions; merely editing the application's permission selection is not proof that an existing token has become restricted.

Ordinary-folder mode retains the existing documented scopes: `disk.info`, `disk.read`, and `disk.write` (all with the `cloud_api:` prefix).

## Configuration and compatibility

Proposed settings:

| Setting | Application-folder mode | Ordinary-folder mode |
|---------|-------------------------|----------------------|
| `storage_mode` | `app_folder` | `disk_folder` |
| `instance_folder` | Required relative subfolder, e.g. `home` | Not used |
| Existing `backup_folder` | Not used | Existing absolute Disk path |
| OAuth token | Existing token input | Existing token input |

New installations should default to application-folder mode. The user supplies a stable, nonempty instance folder name; do not derive it from a token, host address, or mutable display name. Example names are placeholders, not a shared default.

Entries without `storage_mode` must continue to behave as `disk_folder` using the existing `backup_folder` value and `/Home Assistant Backups` fallback. Do not reinterpret an existing entry as application-folder mode or rewrite its path. No data migration is required for this additive compatibility behavior; follow HA config-entry versioning requirements if the final implementation changes the persisted schema.

Provide mode selection and mode-specific fields during initial setup. Changing storage mode or instance folder on an existing entry is outside the first iteration: document adding a new entry with a suitable token. Existing same-token duplicate-entry restrictions remain; this design targets separate HA installations, not multiple entries using one token within one installation.

## Path validation and resolution

Use one resolver for all backup operations:

- Application-folder mode resolves `instance_folder` to `app:/<relative-folder>`.
- Ordinary-folder mode retains its current path semantics.
- Never join an application-relative path with the physical Apps directory.
- Avoid doubled separators when appending archive or metadata filenames.

For `instance_folder`, allow one or more relative path segments, including Unicode names and internal spaces. Reject an empty value, leading/trailing whitespace, leading/trailing `/`, repeated `/`, `.` or `..` segments, backslashes, colons, control characters, and `%` characters. Reject URI/query/fragment delimiters `?` and `#` to keep configured paths literal and unambiguous. Do not URL-decode user input before validation or concatenate it into request URLs; pass it as a path argument to `yadisk`.

Always resolve filenames beneath the chosen base path. Do not accept another `app:/` or `disk:/` prefix through the relative-folder setting. Validate filenames received from outside the path resolver as single filename components before joining; do not permit them to change the configured storage base.

## Backup operations

- Create missing instance-folder ancestors recursively. The current single `mkdir()` is insufficient for a nested relative folder. Verify the installed `yadisk` version's recursive creation behavior with `app:/` before choosing its implementation.
- Do not attempt to create or delete the `app:/` root as an ordinary directory. Distinguish an existing directory from an existing file and from a permissions or connectivity error.
- List only direct backup files in the configured instance folder, preserving existing filtering and metadata behavior; never scan sibling folders.
- Upload the archive and sidecar into the same instance folder using the existing naming convention.
- Download, metadata lookup, backup-ID resolution, and deletion use the same resolved base path.
- Continue moving deleted archives and sidecars to trash rather than permanently deleting them. Confirm this works with the restricted token before release.
- Preserve current handling of old backups and sidecars; changes to backup-ID algorithms are not part of this feature.

## Validation and errors

During application-folder setup, validate both Disk information access and access to the resolved instance directory. Ensure the directory exists, creating it if necessary. Creation during setup is an intentional side effect and must be stated in the form description.

A successful Disk-information request alone does not establish that file operations are authorized. Directory access/creation also does not prove that upload, download, and deletion all work: cover those in the integration test and manual acceptance run rather than creating disposable backup files during setup.

Report authorization failures separately from network errors and invalid folder input. Do not silently fall back from restricted application-folder access to an ordinary Disk path. Never log tokens. If authorization requires replacement, persist the replacement token through HA's config-entry update mechanism; do not report success without saving it.

Keep the existing storage-space check. All instance folders consume the same account quota, and concurrent uploads can invalidate a previously cached capacity result. Handle server-side insufficient-storage errors regardless of the preflight result.

## Existing implementation touchpoints

- `custom_components/yandex_disk_backup/const.py`: storage-mode and relative-folder configuration keys; retain existing defaults for compatibility.
- `config_flow.py`: mode selection, conditional forms, path validation, and mode-aware access checks. Its current validation only calls `get_disk_info()`; identity currently derives from the token prefix and is not an instance-folder namespace.
- `backup.py`: centralized storage-path resolution, recursive directory preparation, and reuse across list/upload/download/get/delete and metadata operations.
- `strings.json` and translations: mode descriptions, folder examples, setup side effects, errors, and the lack of sibling-folder security isolation.
- Tests: configuration compatibility, restricted paths, and every backup operation.
- `README.md`: scope selection for each storage mode and a multi-instance walkthrough.

Before modifying functions, search their callers and confirm assumptions against the current code. Do not introduce unrelated fixes while implementing this design.

## Test and acceptance criteria

Automated tests must cover:

1. Existing entries without a mode retain their configured ordinary path and fallback default.
2. New app-folder entries require a valid explicit instance folder; Unicode names and nested folders work, while invalid paths above are rejected.
3. All file and sidecar operations stay under the resolved instance folder, including ID resolution and error paths.
4. Folder preparation handles existing folders, nested folders, a file occupying the desired path, and authorization/network failures.
5. Setup distinguishes invalid permissions from connectivity errors and never logs secrets.
6. Two agents using `app:/home` and `app:/testing` only list and operate on their own configured files, even when archive filenames match.
7. No application-folder operation accidentally targets `disk:/`, the physical Apps directory, or another instance folder.
8. Insufficient space and trash deletion retain their existing semantics.

Live acceptance with a dedicated test account is a release gate:

- Obtain a token with exactly `cloud_api:disk.app_folder` and `cloud_api:disk.info` and verify its granted scopes where available.
- Verify Disk information, automatic app-root creation, nested-folder creation, listing, archive/sidecar upload, metadata loading, download, and trash deletion.
- Confirm that file reads and writes outside the application folder are denied, using only dedicated test resources.
- Configure two HA instances or equivalent independent clients under the same OAuth application/account, with distinct instance folders; verify separate backup lists and no cross-folder modification during ordinary operations.
- Confirm that different tokens for the same application/account share the expected application folder. Document that either token can access sibling folders, rather than claiming isolation.
- Verify the ordinary-folder mode continues working unchanged.

Do not claim the new scope combination or namespace support is production-tested until this live acceptance has passed. If an operation requires broader privileges, report that as a blocker rather than expanding token scopes silently.

## Migration and rollout

This is opt-in for existing installations and recommended for new ones. Existing archives and sidecars remain in place. A user switching modes creates a new entry and keeps the old location available until they have verified the new backup and restore path. Any manual copying must preserve both archive and sidecar; automated migration and deduplication are out of scope.

Release documentation must explain the security benefit relative to full-Disk access, the shared-folder limitation, the permission change, and the requirement for a token without broad file scopes.

## References and evidence limits

- Yandex application folders: https://yandex.ru/dev/disk-api/doc/ru/concepts/app-folders.md
- Yandex Disk OAuth permissions: https://yandex.ru/dev/disk/api/concepts/quickstart.html
- YaDisk asynchronous API: https://yadisk.readthedocs.io/en/latest/api_reference/async_api.html

Documentation confirms the `app:/` namespace and application-folder permission boundary. Exact behavior of the full backup lifecycle with the selected scopes, multiple tokens, trash operations, and recursive directory creation has not been verified against a real Yandex account in this work.
