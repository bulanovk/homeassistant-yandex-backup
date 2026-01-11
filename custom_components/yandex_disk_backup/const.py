"""Constants for the Yandex Disk backup integration."""

from logging import getLogger

DOMAIN = "yandex_disk_backup"

# Configuration keys
CONF_TOKEN = "token"
CONF_BACKUP_FOLDER = "backup_folder"

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
TO_REDACT = {CONF_TOKEN, "access_token", "refresh_token"}

# Backup agent listeners key in hass.data
DATA_BACKUP_AGENT_LISTENERS = "backup_agent_listeners"
