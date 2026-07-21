from __future__ import annotations

import os
from dataclasses import dataclass

import pytest

from linxira_recovery_diagnostics.commands import (
    FINDMNT_MNT, FINDMNT_ROOT, GRUB_BTRFS_ACTIVE, GRUB_BTRFS_ENABLED, LSBLK,
    CommandResult,
)
from linxira_recovery_diagnostics.collector import EvidenceCollector


@dataclass
class FakeStat:
    st_mtime: float


class FakeReader:
    def __init__(self, files=None, directories=None, mtimes=None):
        self.files = dict(files or {})
        self.directories = {key: tuple(value) for key, value in (directories or {}).items()}
        self.mtimes = dict(mtimes or {})

    def exists(self, path):
        return path in self.files or path in self.directories

    def stat(self, path):
        if path not in self.files and path not in self.directories:
            raise FileNotFoundError(path)
        return FakeStat(self.mtimes.get(path, 0))

    def read_text(self, path, limit=1_000_000):
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path][:limit]

    def entries(self, path):
        return self.directories.get(path, ())


class FakeRunner:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def run(self, argv, timeout=5.0):
        self.calls.append((argv, timeout))
        value = self.results.get(argv)
        if isinstance(value, CommandResult):
            return value
        return CommandResult(argv, 0, value or "")


def mount_json(target="/", fstype="btrfs", available=10 * 1024**3):
    return '{"filesystems":[{"target":"%s","source":"/dev/vda2","fstype":"%s","options":"rw,subvol=@","fsroots":"/@","avail":%d,"used":1000,"size":21474836480}]}' % (target, fstype, available)


def lsblk_json(fstype="btrfs"):
    return '{"blockdevices":[{"name":"vda","path":"/dev/vda","type":"disk","size":30000000000,"children":[{"name":"vda2","path":"/dev/vda2","type":"part","fstype":"%s","uuid":"12345678-1234-1234-1234-123456789abc","mountpoints":["/"]}]}]}' % fstype


@pytest.fixture
def make_collector():
    def factory(*, live=False, fstype="btrfs", available=10 * 1024**3, timeshift=True, timeshift_result=None, extra_files=None, directories=None, mtimes=None):
        files = {
            "/boot/initramfs-linux.img": "",
            "/boot/grub/grub.cfg": "menuentry",
            "/sys/class/net/eth0/operstate": "up\n",
            "/proc/net/route": "Iface Destination\neth0 00000000\n",
        }
        dirs = {
            "/boot": ("initramfs-linux.img", "grub"),
            "/sys/class/net": ("lo", "eth0"),
            "/proc": (),
            "/var/lib/pacman/local": (),
        }
        if live:
            dirs["/run/linxira-live"] = ()
            files.update({
                "/mnt/etc/pacman.conf": "", "/mnt/usr/bin/pacman": "",
                "/mnt/bin/sh": "", "/mnt/etc/fstab": "", "/usr/bin/arch-chroot": "",
            })
        if timeshift:
            files["/usr/bin/timeshift"] = ""
            files["/etc/timeshift/timeshift.json"] = '{"btrfs_mode":"true","backup_device_uuid":"12345678-1234-1234-1234-123456789abc"}'
            dirs["/var/lib/pacman/local"] = ("timeshift-24.06.1-1", "archlinux-keyring-20260701-1")
            files["/var/lib/pacman/local/timeshift-24.06.1-1/desc"] = "%VERSION%\n24.06.1-1\n"
            files["/var/lib/pacman/local/archlinux-keyring-20260701-1/desc"] = "%VERSION%\n20260701-1\n"
        files.update(extra_files or {})
        dirs.update(directories or {})
        results = {
            FINDMNT_ROOT: mount_json("/", fstype, available),
            FINDMNT_MNT: mount_json("/mnt", fstype, available) if live else CommandResult(FINDMNT_MNT, 1, "", "not mounted", "command-failed"),
            LSBLK: lsblk_json(fstype),
            GRUB_BTRFS_ENABLED: "enabled\n",
            GRUB_BTRFS_ACTIVE: "active\n",
        }
        if timeshift:
            from linxira_recovery_diagnostics.commands import TIMESHIFT_LIST
            results[TIMESHIFT_LIST] = timeshift_result or "{\"snapshots\":[]}\n"
        reader = FakeReader(files, dirs, mtimes)
        runner = FakeRunner(results)
        return EvidenceCollector(reader, runner, now=1_784_678_400), reader, runner
    return factory
