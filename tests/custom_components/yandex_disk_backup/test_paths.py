"""Tests for storage path helpers."""

import pytest

from custom_components.yandex_disk_backup.const import (
    CONF_BACKUP_FOLDER,
    CONF_INSTANCE_FOLDER,
    CONF_STORAGE_MODE,
    CONF_TOKEN,
)
from custom_components.yandex_disk_backup.paths import (
    InvalidPathError,
    folder_chain,
    join_filename,
    make_unique_id,
    resolve_base_path,
    validate_instance_folder,
)


@pytest.mark.parametrize("ok", ["home", "Дача 2", "дом/гараж", "a/b/c"])
def test_validate_instance_folder_accepts(ok):
    assert validate_instance_folder(ok) == ok


@pytest.mark.parametrize(
    "bad",
    [
        "",
        " home",
        "home ",
        "/home",
        "home/",
        "a//b",
        ".",
        "a/../b",
        "a/./b",
        "a\\b",
        "app:/x",
        "disk:/x",
        "50%",
        "a?b",
        "a#b",
        "a\x00b",
        "a\nb",
    ],
)
def test_validate_instance_folder_rejects(bad):
    with pytest.raises(InvalidPathError):
        validate_instance_folder(bad)


def test_resolve_app_folder():
    cfg = {CONF_STORAGE_MODE: "app_folder", CONF_INSTANCE_FOLDER: "home"}
    assert resolve_base_path(cfg) == "app:/home"


def test_resolve_legacy_default():
    assert resolve_base_path({CONF_TOKEN: "t"}) == "/Home Assistant Backups"


def test_resolve_legacy_custom():
    assert resolve_base_path({CONF_BACKUP_FOLDER: "/x"}) == "/x"


def test_resolve_disk_mode():
    cfg = {CONF_STORAGE_MODE: "disk_folder", CONF_BACKUP_FOLDER: "/y"}
    assert resolve_base_path(cfg) == "/y"


def test_resolve_app_folder_invalid_raises():
    cfg = {CONF_STORAGE_MODE: "app_folder", CONF_INSTANCE_FOLDER: "../x"}
    with pytest.raises(InvalidPathError):
        resolve_base_path(cfg)


def test_join():
    assert join_filename("app:/home", "b.tar") == "app:/home/b.tar"


def test_join_trailing_slash():
    assert join_filename("/x/", "b.tar") == "/x/b.tar"


@pytest.mark.parametrize("bad", ["", ".", "..", "a/b", "a\\b"])
def test_join_rejects(bad):
    with pytest.raises(InvalidPathError):
        join_filename("app:/home", bad)


def test_join_allows_colon_in_legacy_name():
    assert join_filename("/x", "b 12:00.tar") == "/x/b 12:00.tar"


def test_chain_app_nested():
    assert folder_chain("app:/a/b") == ["app:/a", "app:/a/b"]


def test_chain_legacy():
    assert folder_chain("/Home Assistant Backups") == ["/Home Assistant Backups"]


def test_chain_legacy_nested():
    assert folder_chain("/a/b") == ["/a", "/a/b"]


def test_chain_disk_prefixed():
    assert folder_chain("disk:/a/b") == ["disk:/a", "disk:/a/b"]


def test_chain_app_root_only():
    assert folder_chain("app:/") == []


@pytest.mark.parametrize(
    ("mode", "folder", "expected"),
    [
        ("app_folder", "home", "42:app_folder:home"),
        ("app_folder", "Home Assistant", "42:app_folder:home_assistant"),
        ("app_folder", "Дача 2", "42:app_folder:dacha_2"),
        (
            "disk_folder",
            "/Home Assistant Backups",
            "42:disk_folder:home_assistant_backups",
        ),
    ],
)
def test_make_unique_id_is_ascii_slug(mode, folder, expected):
    assert make_unique_id("42", mode, folder) == expected
