from __future__ import annotations

import json
import os
import stat
import zipfile

import pytest

from linxira_recovery_diagnostics.support import REDACTED, create_support_bundle, redact, support_report


@pytest.mark.parametrize("value", [
    "host.example.test", "alice@example.test", "192.168.10.42", "2001:db8::10",
    "aa:bb:cc:dd:ee:ff", "12345678-1234-1234-1234-123456789abc",
    "0123456789abcdef0123456789abcdef", "https://support.example.test/case?id=secret",
    "/home/alice/Documents/report.txt",
])
def test_redaction_corpus(value):
    assert value not in json.dumps(redact({"value": value}, identities=("host.example.test", "alice")))


@pytest.mark.parametrize("key", ["password", "api_token", "clientSecret", "machine_id", "disk_serial", "ssid", "hostname", "username", "homeDir"])
def test_sensitive_keys_are_recursively_redacted(key):
    value = {"outer": [{key: "must-not-survive"}]}
    assert redact(value, identities=())["outer"][0][key] == REDACTED


def test_support_report_is_allowlisted():
    report = {
        "schema": "x", "schema_version": 1, "generated_at": "now", "mode": {},
        "mounts": {}, "storage": {}, "snapshots": {}, "pacman": {}, "keyring": {},
        "boot": {}, "installed_target": {}, "warnings": [],
        "journal": "must not enter", "cmdline": "root=secret", "unknown": {"token": "x"},
    }
    rendered = json.dumps(support_report(report))
    assert "must not enter" not in rendered
    assert "root=secret" not in rendered
    assert "unknown" not in rendered


def test_bundle_private_atomic_and_contains_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    report = {"schema": "x", "schema_version": 1, "generated_at": "now", "mode": {}, "mounts": {}, "storage": {}, "snapshots": {}, "pacman": {}, "keyring": {}, "boot": {}, "installed_target": {}, "warnings": []}
    path, manifest = create_support_bundle(report)
    assert path.parent == tmp_path / "linxira-recovery-diagnostics" / "bundles"
    assert manifest["privacy"]["upload"] is False
    assert not list(path.parent.glob("*.tmp"))
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    with zipfile.ZipFile(path) as archive:
        assert set(archive.namelist()) == {"manifest.json", "report.json"}
        assert "journal" not in archive.read("report.json").decode()


def test_refuses_symlinked_application_state(tmp_path, monkeypatch):
    target = tmp_path / "target"
    target.mkdir()
    state = tmp_path / "linxira-recovery-diagnostics"
    try:
        state.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    with pytest.raises(RuntimeError, match="symlinked"):
        create_support_bundle({})
