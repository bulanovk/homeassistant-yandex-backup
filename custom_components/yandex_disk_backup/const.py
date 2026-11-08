"""Constants for the Yandex Disk backup integration."""

from logging import getLogger

DOMAIN = "yandex_disk_backup"

# Configuration keys
CONF_TOKEN = "token"
CONF_BACKUP_FOLDER = "backup_folder"
CONF_STORAGE_MODE = "storage_mode"
CONF_INSTANCE_FOLDER = "instance_folder"
CONF_AUTH_METHOD = "auth_method"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_EXPIRES_AT = "expires_at"
# Written only by device-flow builds that were never released. Entries that still
# carry them lose them on reauthentication; diagnostics redact the secret.
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_DEVICE_ID = "device_id"

# Storage modes and auth methods
STORAGE_MODE_APP_FOLDER = "app_folder"
STORAGE_MODE_DISK_FOLDER = "disk_folder"  # legacy: manual token only
AUTH_METHOD_DEVICE = "device"  # unreleased builds: setup requires a new sign-in
AUTH_METHOD_MANUAL = "manual"
AUTH_METHOD_OAUTH = "oauth"  # built-in app, PKCE

APP_FOLDER_ROOT = "app:/"

# OAuth scopes per storage mode
SCOPES_APP_FOLDER = ("cloud_api:disk.app_folder", "cloud_api:disk.info")
SCOPES_DISK_FOLDER = (
    "cloud_api:disk.info",
    "cloud_api:disk.read",
    "cloud_api:disk.write",
)

# Yandex OAuth endpoints
OAUTH_TOKEN_URL = "https://oauth.yandex.ru/token"
# Built-in public OAuth app used for app-folder storage. Authorization uses
# PKCE through Home Assistant's OAuth2 flow, so no client secret is shipped.
APP_CLIENT_ID = "b9139576c46c42299689392fc6356937"
OAUTH_AUTHORIZE_URL = "https://oauth.yandex.ru/authorize"


# Refresh the token when fewer than 30 days remain
TOKEN_REFRESH_MARGIN = 30 * 24 * 3600

# Key of the token manager inside entry.runtime_data
RUNTIME_TOKEN_MANAGER = "token_manager"

# Defaults
DEFAULT_BACKUP_FOLDER = "/Home Assistant Backups"

# Timeouts (in seconds)
UPLOAD_TIMEOUT = 300
DOWNLOAD_TIMEOUT = 300
LIST_TIMEOUT = 30
DELETE_TIMEOUT = 30

# Chunk size for streaming downloads (4 MB to match HA backup patterns)
CHUNK_SIZE = 4 * 1024 * 1024

# Backup file extensions
BACKUP_EXTENSIONS = (".tar", ".tar.gz")

# Logging
_LOGGER = getLogger(__name__)

# Data to redact from diagnostics
TO_REDACT = {CONF_TOKEN, "access_token", "refresh_token", CONF_CLIENT_SECRET}

# Backup agent listeners key in hass.data
DATA_BACKUP_AGENT_LISTENERS = "backup_agent_listeners"
