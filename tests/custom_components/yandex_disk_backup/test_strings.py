"""Consistency checks for UI strings used by the config flow."""

import json
from pathlib import Path

COMPONENT = (
    Path(__file__).resolve().parents[3] / "custom_components" / "yandex_disk_backup"
)


def _load(name: str) -> dict:
    return json.loads((COMPONENT / name).read_text(encoding="utf-8"))


def test_strings_cover_flow():
    config = _load("strings.json")["config"]
    steps = config["step"]
    for step in (
        "user",
        "manual_token",
        "folder",
        "reauth_confirm",
        "reauth_oauth",
        "reconfigure",
        "migration_hint",
    ):
        assert step in steps, step

    for removed in (
        "auth_method",
        "device_auth",
        "device_wait",
        "device_expired",
        "reauth_device",
    ):
        assert removed not in steps, removed
    assert "progress" not in config

    for error in (
        "invalid_token",
        "cannot_connect",
        "unknown",
        "invalid_instance_folder",
        "folder_is_file",
    ):
        assert error in config["error"], error

    for abort in (
        "already_configured",
        "reauth_successful",
        "wrong_account",
        "cannot_connect",
    ):
        assert abort in config["abort"], abort


def test_selector_options_cover_choices():
    selector = _load("strings.json")["selector"]
    assert set(selector["storage_mode"]["options"]) == {"app_folder", "disk_folder"}
    # Storage mode decides the sign-in: no auth_method selector any more.
    assert "auth_method" not in selector


def test_disk_folder_is_labelled_legacy():
    options = _load("strings.json")["selector"]["storage_mode"]["options"]
    assert "legacy" in options["disk_folder"].lower()
    ru = _load("translations/ru.json")["selector"]["storage_mode"]["options"]
    assert "легаси" in ru["disk_folder"]


def test_translations_match_strings():
    assert _load("strings.json") == _load("translations/en.json")


def _leaves(node, path=()):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaves(value, path + (key,))
    else:
        yield path, node


def test_no_angle_brackets_in_strings():
    """HA frontend rejects <...> in markdown as INVALID_TAG."""
    for name in ("strings.json", "translations/en.json", "translations/ru.json"):
        for path, text in _leaves(_load(name)):
            assert "<" not in text, (name, path)


def test_russian_keys_match_english():
    en = {path for path, _ in _leaves(_load("translations/en.json"))}
    ru = {path for path, _ in _leaves(_load("translations/ru.json"))}
    assert ru == en
