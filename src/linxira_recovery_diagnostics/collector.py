from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

from .commands import (
    FINDMNT_MNT, FINDMNT_ROOT, GRUB_BTRFS_ACTIVE, GRUB_BTRFS_ENABLED,
    LSBLK, TIMESHIFT_LIST, CommandResult, FixedCommandRunner,
)
from .system import SystemReader, package_version

REPORT_SCHEMA = "org.linxira.recovery-diagnostics.report"
LOW_SPACE_BYTES = 2 * 1024**3
PACKAGE_PROCESSES = frozenset({"pacman", "makepkg", "pamac", "pamac-daemon", "yay", "paru", "pkcon", "packagekitd"})


def _command_evidence(result: CommandResult, include_stdout: bool = False) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "argv": list(result.argv),
        "ok": result.returncode == 0,
        "returncode": result.returncode,
    }
    if result.warning:
        evidence["warning"] = result.warning
    if result.stderr:
        evidence["stderr_summary"] = result.stderr.strip().splitlines()[0][:240]
    if include_stdout:
        evidence["stdout"] = result.stdout
    return evidence


def _json_output(result: CommandResult) -> Any:
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        return None


def _read_json(reader: SystemReader, path: str) -> dict[str, Any] | None:
    try:
        value = json.loads(reader.read_text(path))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _config_keys(reader: SystemReader, paths: tuple[str, ...]) -> dict[str, Any]:
    allowed = {"GRUB_BTRFS_MKCONFIG", "GRUB_BTRFS_SCRIPT_CHECK", "GRUB_BTRFS_SHOW_SNAPSHOTS_FOUND"}
    for path in paths:
        if not reader.exists(path):
            continue
        values: dict[str, str] = {}
        try:
            lines = reader.read_text(path, 128_000).splitlines()
        except OSError:
            return {"present": True, "path": path, "readable": False, "values": {}}
        for line in lines:
            match = re.match(r"^\s*([A-Z0-9_]+)=(.*)$", line)
            if match and match.group(1) in allowed:
                values[match.group(1)] = match.group(2).strip().strip("\"'")[:256]
        return {"present": True, "path": path, "readable": True, "values": values}
    return {"present": False, "paths_checked": list(paths), "values": {}}


def _flatten_devices(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flat: list[dict[str, Any]] = []
    for device in devices:
        flat.append(device)
        children = device.get("children")
        if isinstance(children, list):
            flat.extend(_flatten_devices([item for item in children if isinstance(item, dict)]))
    return flat


class EvidenceCollector:
    def __init__(self, reader: SystemReader | None = None, runner: FixedCommandRunner | None = None, now: float | None = None):
        self.reader = reader or SystemReader()
        self.runner = runner or FixedCommandRunner()
        self.now = time.time() if now is None else now

    def collect(self) -> dict[str, Any]:
        live_markers = [path for path in ("/run/archiso", "/run/linxira-live") if self.reader.exists(path)]
        root_result = self.runner.run(FINDMNT_ROOT)
        mnt_result = self.runner.run(FINDMNT_MNT)
        lsblk_result = self.runner.run(LSBLK)
        root_mount = self._mount(root_result)
        mnt_mount = self._mount(mnt_result)
        devices_json = _json_output(lsblk_result) or {}
        devices = devices_json.get("blockdevices", []) if isinstance(devices_json, dict) else []
        devices = devices if isinstance(devices, list) else []
        flat_devices = _flatten_devices([d for d in devices if isinstance(d, dict)])

        return {
            "schema": REPORT_SCHEMA,
            "schema_version": 1,
            "generated_at": datetime.fromtimestamp(self.now, timezone.utc).isoformat(),
            "mode": {"live": bool(live_markers), "markers": live_markers},
            "mounts": {
                "root": {"evidence": _command_evidence(root_result), "filesystem": root_mount},
                "installed_target": {"evidence": _command_evidence(mnt_result), "filesystem": mnt_mount},
            },
            "storage": self._storage(lsblk_result, flat_devices, root_mount, mnt_mount),
            "snapshots": self._snapshots(),
            "pacman": self._pacman(),
            "keyring": self._keyring(),
            "boot": self._boot(),
            "installed_target": self._chroot_readiness(bool(live_markers), mnt_mount),
            "warnings": self._warnings(bool(live_markers), root_mount, mnt_mount),
        }

    @staticmethod
    def _mount(result: CommandResult) -> dict[str, Any] | None:
        value = _json_output(result)
        filesystems = value.get("filesystems", []) if isinstance(value, dict) else []
        return filesystems[0] if isinstance(filesystems, list) and filesystems else None

    def _storage(self, result: CommandResult, devices: list[dict[str, Any]], root: dict[str, Any] | None, mnt: dict[str, Any] | None) -> dict[str, Any]:
        btrfs = [d for d in devices if str(d.get("fstype", "")).lower() == "btrfs"]
        layouts = []
        for mount in (root, mnt):
            if mount and str(mount.get("fstype", "")).lower() == "btrfs":
                layouts.append({
                    "target": mount.get("target"), "source": mount.get("source"),
                    "subvolume": mount.get("fsroots"), "options": mount.get("options"),
                })
        spaces = [self._space(item) for item in (root, mnt) if item]
        return {
            "evidence": _command_evidence(result),
            "devices": devices,
            "btrfs": {"detected": bool(btrfs or layouts), "device_count": len(btrfs), "layouts": layouts},
            "space": spaces,
        }

    @staticmethod
    def _space(mount: dict[str, Any]) -> dict[str, Any]:
        def number(key: str) -> int | None:
            try:
                return int(mount[key])
            except (KeyError, TypeError, ValueError):
                return None
        available, size = number("avail"), number("size")
        low = available is not None and (available < LOW_SPACE_BYTES or (size and available / size < 0.10))
        return {"target": mount.get("target"), "available_bytes": available, "used_bytes": number("used"), "size_bytes": size, "low": bool(low)}

    def _snapshots(self) -> dict[str, Any]:
        version = package_version(self.reader, "timeshift")
        config = _read_json(self.reader, "/etc/timeshift/timeshift.json")
        target_version = package_version(self.reader, "timeshift", "/mnt")
        target_config = _read_json(self.reader, "/mnt/etc/timeshift/timeshift.json")
        selected = {}
        if config:
            for key in ("backup_device_uuid", "btrfs_mode", "schedule_monthly", "schedule_weekly", "schedule_daily", "schedule_hourly", "schedule_boot"):
                if key in config:
                    selected[key] = config[key]
        timeshift_evidence: dict[str, Any] = {"attempted": False}
        if self.reader.exists("/usr/bin/timeshift"):
            result = self.runner.run(TIMESHIFT_LIST, timeout=15.0)
            timeshift_evidence = _command_evidence(result, include_stdout=result.returncode == 0)
            timeshift_evidence["attempted"] = True
        enabled = self.runner.run(GRUB_BTRFS_ENABLED)
        active = self.runner.run(GRUB_BTRFS_ACTIVE)
        return {
            "timeshift": {
                "installed": version is not None, "version": version,
                "config_present": config is not None, "config": selected,
                "installed_target": {"installed": target_version is not None, "version": target_version, "config_present": target_config is not None},
                "list": timeshift_evidence,
            },
            "grub_btrfs": {
                "config": _config_keys(self.reader, ("/etc/default/grub-btrfs/config", "/etc/grub-btrfs/config")),
                "service_enabled": _command_evidence(enabled, include_stdout=True),
                "service_active": _command_evidence(active, include_stdout=True),
            },
        }

    def _pacman(self) -> dict[str, Any]:
        lock_path = "/var/lib/pacman/db.lck"
        exists, age = self.reader.exists(lock_path), None
        if exists:
            try:
                age = max(0, int(self.now - self.reader.stat(lock_path).st_mtime))
            except OSError:
                pass
        processes = []
        for entry in self.reader.entries("/proc"):
            if not entry.isdigit():
                continue
            try:
                comm = self.reader.read_text(f"/proc/{entry}/comm", 128).strip()
                cmd_name = self.reader.read_text(f"/proc/{entry}/cmdline", 4096).split("\0", 1)[0].rsplit("/", 1)[-1]
            except OSError:
                continue
            matched = comm if comm in PACKAGE_PROCESSES else cmd_name if cmd_name in PACKAGE_PROCESSES else None
            if matched:
                processes.append({"pid": int(entry), "program": matched})
        processes.sort(key=lambda item: item["pid"])
        return {"lock": {"exists": exists, "age_seconds": age, "stale_candidate": bool(exists and age is not None and age >= 7200 and not processes)}, "active_package_processes": processes}

    def _keyring(self) -> dict[str, Any]:
        utc_year = datetime.fromtimestamp(self.now, timezone.utc).year
        interface_up = False
        for name in self.reader.entries("/sys/class/net"):
            if name == "lo":
                continue
            try:
                interface_up |= self.reader.read_text(f"/sys/class/net/{name}/operstate", 32).strip() in {"up", "unknown"}
            except OSError:
                pass
        route = ""
        try:
            route = self.reader.read_text("/proc/net/route", 256_000)
        except OSError:
            pass
        default_route = any(len(line.split()) > 1 and line.split()[1] == "00000000" for line in route.splitlines()[1:])
        return {
            "package": "archlinux-keyring", "version": package_version(self.reader, "archlinux-keyring"),
            "installed_target_version": package_version(self.reader, "archlinux-keyring", "/mnt"),
            "prerequisites": {"clock_sane": utc_year >= 2024, "utc_time": datetime.fromtimestamp(self.now, timezone.utc).isoformat(), "network_interface_up": interface_up, "default_ipv4_route": default_route},
        }

    def _boot(self) -> dict[str, Any]:
        boot_entries = tuple(self.reader.entries("/boot"))
        initramfs = sorted(name for name in boot_entries if name.startswith("initramfs-") and name.endswith(".img"))
        target_entries = tuple(self.reader.entries("/mnt/boot"))
        target_initramfs = sorted(name for name in target_entries if name.startswith("initramfs-") and name.endswith(".img"))
        return {
            "initramfs_images": initramfs, "initramfs_present": bool(initramfs),
            "grub_config_present": self.reader.exists("/boot/grub/grub.cfg"),
            "efi_directory_present": self.reader.exists("/boot/efi") or self.reader.exists("/efi"),
            "installed_target": {
                "initramfs_images": target_initramfs, "initramfs_present": bool(target_initramfs),
                "grub_config_present": self.reader.exists("/mnt/boot/grub/grub.cfg"),
                "efi_directory_present": self.reader.exists("/mnt/boot/efi") or self.reader.exists("/mnt/efi"),
            },
        }

    def _chroot_readiness(self, live: bool, mount: dict[str, Any] | None) -> dict[str, Any]:
        checks = {
            "target_mounted": bool(mount),
            "pacman_config": self.reader.exists("/mnt/etc/pacman.conf"),
            "target_pacman": self.reader.exists("/mnt/usr/bin/pacman"),
            "target_shell": self.reader.exists("/mnt/bin/sh"),
            "target_fstab": self.reader.exists("/mnt/etc/fstab"),
            "host_arch_chroot": self.reader.exists("/usr/bin/arch-chroot"),
        }
        return {"applicable": live, "fixed_target": "/mnt", "checks": checks, "ready": bool(live and all(checks.values()))}

    @staticmethod
    def _warnings(live: bool, root: dict[str, Any] | None, mnt: dict[str, Any] | None) -> list[str]:
        warnings = []
        if root is None:
            warnings.append("root-mount-evidence-unavailable")
        if live and mnt is None:
            warnings.append("installed-target-not-mounted")
        return warnings
