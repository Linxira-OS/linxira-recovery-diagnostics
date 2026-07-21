from __future__ import annotations

import getpass
import io
import json
import os
import re
import secrets
import socket
import stat
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REDACTED = "[REDACTED]"
SENSITIVE_KEY = re.compile(r"(?:token|password|passwd|secret|authorization|cookie|api[_-]?key|machine[_-]?id|serial|ssid|hostname|user(?:name)?|home(?:dir)?)", re.I)
PATTERNS = (
    re.compile(r"https?://[^\s\]\[\"'<>]+", re.I),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    re.compile(r"\b(?:[0-9A-F]{2}:){5}[0-9A-F]{2}\b", re.I),
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    re.compile(r"(?<![\w:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?![\w:])", re.I),
    re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I),
    re.compile(r"\b[0-9a-f]{32}\b", re.I),
)


def _identities() -> tuple[str, ...]:
    values = {getpass.getuser(), socket.gethostname(), str(Path.home())}
    home = str(Path.home())
    values.add(home.replace("\\", "/"))
    return tuple(sorted((value for value in values if value and len(value) >= 3), key=len, reverse=True))


def redact(value: Any, identities: tuple[str, ...] | None = None) -> Any:
    identities = _identities() if identities is None else identities
    if isinstance(value, dict):
        return {str(key): REDACTED if SENSITIVE_KEY.search(str(key)) else redact(item, identities) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, identities) for item in value]
    if isinstance(value, tuple):
        return [redact(item, identities) for item in value]
    if not isinstance(value, str):
        return value
    output = value
    for identity in identities:
        output = re.sub(re.escape(identity), REDACTED, output, flags=re.I)
    output = re.sub(r"(?i)(?:/home/|/Users/)[^/\s]+", "/home/" + REDACTED, output)
    for pattern in PATTERNS:
        output = pattern.sub(REDACTED, output)
    return output


def support_report(report: dict[str, Any]) -> dict[str, Any]:
    """Build an explicit allowlist; command output and raw logs never enter bundles."""
    storage = report.get("storage", {})
    snapshots = report.get("snapshots", {})
    timeshift = snapshots.get("timeshift", {})
    grub_btrfs = snapshots.get("grub_btrfs", {})
    allowed = {
        "schema": report.get("schema"),
        "schema_version": report.get("schema_version"),
        "generated_at": report.get("generated_at"),
        "mode": report.get("mode"),
        "mounts": {
            key: {"filesystem": value.get("filesystem"), "evidence_ok": value.get("evidence", {}).get("ok")}
            for key, value in report.get("mounts", {}).items() if isinstance(value, dict)
        },
        "storage": {"btrfs": storage.get("btrfs"), "space": storage.get("space")},
        "snapshots": {
            "timeshift": {key: timeshift.get(key) for key in ("installed", "version", "config_present", "config", "installed_target")},
            "grub_btrfs": {
                "config": grub_btrfs.get("config"),
                "service_enabled": grub_btrfs.get("service_enabled", {}).get("ok"),
                "service_active": grub_btrfs.get("service_active", {}).get("ok"),
            },
        },
        "pacman": report.get("pacman"),
        "keyring": report.get("keyring"),
        "boot": report.get("boot"),
        "installed_target": report.get("installed_target"),
        "warnings": report.get("warnings"),
    }
    return redact(allowed)


def state_directory() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "linxira-recovery-diagnostics"


def _private_directory(path: Path) -> None:
    root = state_directory()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise RuntimeError("private output escaped the application state directory") from error
    if root.is_symlink():
        raise RuntimeError("refusing symlinked private state directory")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("private state path is not a real directory")
    os.chmod(root, 0o700)
    if path.exists() and path.is_symlink():
        raise RuntimeError("refusing symlinked private state directory")
    path.mkdir(mode=0o700, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError("private state path is not a real directory")
    os.chmod(path, 0o700)
    if os.name == "posix" and stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise RuntimeError("private state directory permissions are not 0700")


def _atomic_write(directory: Path, filename: str, data: bytes) -> Path:
    _private_directory(directory)
    destination = directory / filename
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("generated destination already exists")
    temporary = directory / ("." + filename + "." + secrets.token_hex(8) + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
        if os.name == "posix":
            directory_fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    return destination


def preview_manifest(report: dict[str, Any]) -> dict[str, Any]:
    filtered = support_report(report)
    return {
        "schema": "org.linxira.recovery-diagnostics.support-manifest",
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": [{"name": "report.json", "media_type": "application/json"}],
        "privacy": {"structured_allowlist": True, "recursive_redaction": True, "raw_journal": False, "raw_dmesg": False, "raw_cmdline": False, "upload": False},
        "report_sections": sorted(filtered),
    }


def create_support_bundle(report: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    filtered = support_report(report)
    manifest = preview_manifest(report)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        archive.writestr("report.json", json.dumps(filtered, indent=2, sort_keys=True) + "\n")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = _atomic_write(state_directory() / "bundles", f"support-{stamp}-{secrets.token_hex(4)}.zip", buffer.getvalue())
    return path, manifest


def save_plan(plan: dict[str, Any]) -> Path:
    plan_id = str(plan["plan_id"]).rsplit(".", 2)[-2]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    data = (json.dumps(plan, indent=2, sort_keys=True) + "\n").encode()
    return _atomic_write(state_directory() / "plans", f"plan-{plan_id}-{stamp}-{secrets.token_hex(4)}.json", data)
