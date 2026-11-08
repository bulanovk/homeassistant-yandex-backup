"""Recursive folder creation on Yandex Disk."""

from yadisk import AsyncClient
from yadisk.exceptions import PathExistsError

from .paths import folder_chain


class FolderIsFileError(Exception):
    """Raised when a folder path is occupied by a regular file."""

    def __init__(self, path: str) -> None:
        """Store the offending path."""
        super().__init__(path)
        self.path = path


async def async_ensure_folder(client: AsyncClient, base_path: str) -> None:
    """Create every folder level of base_path that does not exist yet.

    Raises:
        FolderIsFileError: a path level exists as a file
        YaDiskError: any other Yandex Disk error
    """
    for path in folder_chain(base_path):
        try:
            await client.mkdir(path)
        except PathExistsError:
            meta = await client.get_meta(path)
            if meta.type != "dir":
                raise FolderIsFileError(path) from None
