# Application-folder storage for multiple Home Assistant instances

Date: 2026-11-05
Status: Sign-in with the built-in app and token refresh without `client_secret` were confirmed by manual testing on 2026-11-07. The other live acceptance checks below remain open.
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
- Do not implement central coordination between HA instances.

## Token acquisition

- Tokens are obtained in the config flow via Yandex OAuth sign-in (PKCE) with the built-in public app (`APP_CLIENT_ID`, no client secret). The device-code flow was never released and is removed; entries it created are not refreshed and ask for a new sign-in.
- Scopes are passed explicitly per storage mode (app folder: `cloud_api:disk.app_folder cloud_api:disk.info`; disk folder: `cloud_api:disk.info cloud_api:disk.read cloud_api:disk.write`).
- The access token, refresh token and expiry are stored in the config entry. The token is refreshed when fewer than 30 days remain; `invalid_grant` starts reauthentication.
- App-folder storage has no manual-token option: sign-in is the built-in app with PKCE only. A pasted token remains for disk-folder (legacy) storage, and legacy disk-folder entries reauthenticate with a token.
- `unique_id`: manual-token entries use the first 8 characters of the token, as on main (no migration); PKCE entries use `<yandex uid>:<storage_mode>:<folder>`; legacy entries keep their existing `unique_id`.

Release gates (verified live, not assumed):
- Sign-in with the built-in app (PKCE) completes on a real Yandex account. Confirmed by manual test, 2026-11-07.
- Token refresh works without `client_secret`. Confirmed by manual test, 2026-11-07.
- The `app:/` folder is visible in the Yandex Disk web interface. Confirmed by manual test, 2026-11-07.

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
| Authorization | Sign-in with the built-in app (PKCE, no client secret) | Manual token with full disk access (legacy) |

New installations should default to application-folder mode. The user supplies a stable, nonempty instance folder name; do not derive it from a token, host address, or mutable display name. Example names are placeholders, not a shared default.

Entries without `storage_mode` must continue to behave as `disk_folder` using the existing `backup_folder` value and `/Home Assistant Backups` fallback. Do not reinterpret an existing entry as application-folder mode or rewrite its path. No data migration is required for this additive compatibility behavior; follow HA config-entry versioning requirements if the final implementation changes the persisted schema.

Provide mode selection and mode-specific fields during initial setup. Reconfigure changes the storage mode or the folder of an existing entry. It repeats authorization and replaces the stored token. When the backup location changes, the setup shows the old and new paths and moves nothing; the user moves the files manually. Existing same-token duplicate-entry restrictions remain; this design targets separate HA installations, not multiple entries using one token within one installation.

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

This is opt-in for existing installations and recommended for new ones. A migration guide for existing instances with full-Disk permissions is a required deliverable of the feature. Status: not yet published; the README points to the Reconfigure hint instead. Automated migration and deduplication remain out of scope. The following is the required manual migration procedure; validate it in live acceptance before publishing it as a tested walkthrough.

### 1. Inventory and prepare

- Record each HA instance's current OAuth application, account, source folder, and intended unique destination subfolder. Existing instances may use different OAuth applications; the target design uses one selected application. Do not assume that their existing `app:/` namespaces are the same.
- Preserve the current working configuration and access to its token securely. Never put tokens into migration logs or the mapping document. Keep backup encryption keys/emergency kits independently available; moving an encrypted archive does not remove the need for its key.
- Identify which backups belong to each instance before copying. If multiple instances already share one source folder, do not guess ownership or split files by filename alone: use known backup metadata and the user's inventory. Leave ambiguous backups untouched until ownership is established.
- Pause scheduled backups and retention/deletion affecting both migration locations on participating instances, and wait for in-flight uploads to finish. Avoid copying an archive while its sidecar is still being written. Keep the pause window short and explicit.
- Check sufficient space for both source and copied destination data. All folders share the account quota; this is a copy-first procedure, not a space-saving move.

### 2. Prepare the restricted destination

- Select the shared target OAuth application and authorize a new token requesting only `cloud_api:disk.app_folder` and `cloud_api:disk.info`. A currently broad token must not be reused as proof of reduced privileges.
- If the same application must temporarily support legacy broad tokens, use an explicit limited-scope authorization request for the new token and verify the resulting permissions. Exact issuance and revocation behavior must be established in live acceptance; do not remove permissions from the application globally or revoke grants while legacy instances still depend on them. If safe coexistence cannot be demonstrated, use a new shared target application for all migrated instances, keeping the old application(s) intact until cutover completes. This remains one shared target application, not one target application per instance.
- Add a new integration entry in application-folder mode using the new token and the chosen instance folder. Keep the old entry available for rollback, but do not select the new location for scheduled backups yet. Setup creates/accesses the destination folder.
- Verify that the new entry can coexist with the old entry. The current token-prefix identity scheme can cause duplicate-entry conflicts; a collision is an implementation/acceptance blocker to resolve safely, not a reason to edit HA storage files manually or remove a working entry prematurely.

### 3. Copy existing backups without changing their identity

- Through the authenticated Yandex Disk user interface, copy each instance's archives and associated metadata files from its recorded source folder into its prepared application subfolder. The user can access both locations; the restricted integration token cannot read the old ordinary folder and must not be used to perform this cross-boundary copy.
- Locate the actual destination created for the selected OAuth application; its displayed name can vary. Do not create a similarly named ordinary folder and assume it is the application's folder. API-based migration tooling, if added later, must resolve `app:/` with the target application's token before acting.
- Copy rather than move. Preserve exact filenames, archive contents, sidecar contents, backup IDs, dates, and encryption state. Use existing sidecar filenames; do not derive them with a new naming algorithm. For a legacy backup without a sidecar, preserve that absence and verify legacy retrieval explicitly; do not invent metadata.
- Never overwrite a destination conflict silently. Skip only if archive and available sidecar are verified identical; otherwise stop for manual resolution. Do not rename one member of an archive/sidecar pair to resolve a conflict.
- Keep a token-free checklist of copied files and compare sizes and, where available, content hashes. Counts and matching filenames alone are insufficient verification. Refresh HA's backup listing after copying; do not modify its internal storage files.

### 4. Validate and cut over one instance at a time

- Verify imported backup names, IDs, dates, sizes, and protection state in the destination. During coexistence, the same backup may appear at two locations; that is expected, not a reason to delete it.
- Download at least one copied backup through the new entry and verify it against the source. Verify that encryption material is available and perform a restore test in a separate disposable HA environment where practical, never an unsolicited restore over the production instance. Test at least one backup without a sidecar if such files are being migrated; inability to retrieve it is a blocker for retiring the old location, not permission to fabricate metadata.
- Create a new backup at the destination, verify its sidecar and download, and test trash deletion only on a disposable test backup. Confirm operations do not modify another instance's subfolder.
- Select only the new entry for that instance's future scheduled backups and configure retention for the intended destination. Re-enable scheduling, run a scheduled backup, and verify it reaches the correct subfolder. Ensure the old entry is not still selected for automatic uploads.
- Repeat for the remaining instances using distinct subfolders. Do not grant application-folder tokens broad read/write permissions to work around an error.

### 5. Retire broad access and clean up separately

- After each instance's cutover succeeds, disable its old integration entry where supported, or remove it once its settings have been recorded securely. Confirm this does not delete remote backups. Keep original backup data until the user's retention/verification window has elapsed; this design does not select an automatic deletion deadline.
- Revoke the old broad credentials only after every consumer of those credentials or the associated application grant has migrated. Inventory shared use first: do not assume revoking one authorization leaves other tokens or instances unaffected. Confirm revocation behavior and verify that the new restricted tokens still function afterwards.
- Updating the OAuth application's configured permission list alone is not proof that older broad credentials are invalid. Verify old access has actually been revoked and verify the new token cannot access ordinary folders outside `app:/`, using dedicated test files.
- Source cleanup is a separate, explicit user action after successful verification, not an automatic part of setup. Account for trash usage when planning space; moving files to trash may not immediately reclaim quota.

### Rollback

Before retiring the old credentials, stop new-location scheduling, restore the old entry as the selected backup location, and resume scheduling there. Original archives remain intact because migration copied rather than moved them. Backups created only after cutover remain at the destination; preserve and inventory them rather than silently assuming the source is current. Keep the new entry available for their retrieval if necessary.

After old credentials are revoked, rollback to ordinary-folder mode requires a fresh authorization with suitable broad scopes. Do not promise immediate rollback using a revoked token. Never delete either location as part of rollback or copy new-only backups back without checking conflicts and preserving their sidecars.

### Migration acceptance gates

Before releasing the guide, exercise: an existing broad-token installation; multiple source instances sharing one target OAuth application; token coexistence and revocation; exact archive/sidecar preservation; encrypted backups; legacy files without sidecars; interrupted/repeated copies and conflicts; rollback before and after revocation; quota pressure; and restoration of scheduling/retention. If a legacy compatibility issue blocks retrieval, document it as a blocker and retain the original working entry until resolved.

Release documentation must explain the security benefit relative to full-Disk access, the shared-folder limitation, the permission change, and the requirement for a token without broad file scopes.

## References and evidence limits

- Yandex application folders: https://yandex.ru/dev/disk-api/doc/ru/concepts/app-folders.md
- Yandex Disk OAuth permissions: https://yandex.ru/dev/disk/api/concepts/quickstart.html
- YaDisk asynchronous API: https://yadisk.readthedocs.io/en/latest/api_reference/async_api.html

Documentation confirms the `app:/` namespace and application-folder permission boundary. On 2026-11-07, PKCE sign-in, token refresh without a client secret, and `app:/` visibility were verified on a real account. Still open: the backup lifecycle checks on a live entry (list, download, delete, get), recursive folder creation with nested folders, multiple tokens and instances, and denial of access outside `app:/`.
