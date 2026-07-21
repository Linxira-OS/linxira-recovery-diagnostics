from __future__ import annotations

from linxira_recovery_diagnostics.commands import FINDMNT_MNT, FINDMNT_ROOT, LSBLK, TIMESHIFT_LIST, CommandResult


def test_installed_btrfs_report_schema(make_collector):
    collector, _, _ = make_collector()
    report = collector.collect()
    assert report["schema_version"] == 1
    assert report["mode"] == {"live": False, "markers": []}
    assert report["storage"]["btrfs"]["detected"] is True
    assert report["snapshots"]["timeshift"]["version"] == "24.06.1-1"


def test_live_target_readiness(make_collector):
    collector, _, _ = make_collector(live=True)
    report = collector.collect()
    assert report["mode"]["live"] is True
    assert report["installed_target"]["fixed_target"] == "/mnt"
    assert report["installed_target"]["ready"] is True
    assert "installed_target" in report["boot"]


def test_non_btrfs(make_collector):
    collector, _, _ = make_collector(fstype="ext4")
    assert collector.collect()["storage"]["btrfs"]["detected"] is False


def test_low_space(make_collector):
    collector, _, _ = make_collector(available=512 * 1024**2)
    assert collector.collect()["storage"]["space"][0]["low"] is True


def test_timeshift_failure_warning(make_collector):
    failed = CommandResult(TIMESHIFT_LIST, None, warning="timeout")
    collector, _, _ = make_collector(timeshift_result=failed)
    evidence = collector.collect()["snapshots"]["timeshift"]["list"]
    assert evidence["warning"] == "timeout"
    assert evidence["attempted"] is True


def test_stale_and_active_locks(make_collector):
    now = 1_784_678_400
    files = {"/var/lib/pacman/db.lck": "", "/proc/42/comm": "pacman\n", "/proc/42/cmdline": "/usr/bin/pacman\0-Syu\0topsecret"}
    collector, _, _ = make_collector(extra_files=files, directories={"/proc": ("42",)}, mtimes={"/var/lib/pacman/db.lck": now - 9000})
    pacman = collector.collect()["pacman"]
    assert pacman["lock"]["stale_candidate"] is False
    assert pacman["active_package_processes"] == [{"pid": 42, "program": "pacman"}]
    assert "topsecret" not in str(pacman)


def test_stale_inactive_lock(make_collector):
    collector, _, _ = make_collector(extra_files={"/var/lib/pacman/db.lck": ""}, mtimes={"/var/lib/pacman/db.lck": 1_784_668_400})
    assert collector.collect()["pacman"]["lock"]["stale_candidate"] is True


def test_keyring_prerequisites(make_collector):
    collector, _, _ = make_collector()
    keyring = collector.collect()["keyring"]
    assert keyring["version"] == "20260701-1"
    assert keyring["prerequisites"]["clock_sane"] is True
    assert keyring["prerequisites"]["network_interface_up"] is True
    assert keyring["prerequisites"]["default_ipv4_route"] is True


def test_collector_uses_fixed_storage_argv(make_collector):
    collector, _, runner = make_collector()
    collector.collect()
    called = [item[0] for item in runner.calls]
    assert called[:3] == [FINDMNT_ROOT, FINDMNT_MNT, LSBLK]
    assert all(isinstance(argv, tuple) for argv in called)
