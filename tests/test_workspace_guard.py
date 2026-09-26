from __future__ import annotations

import json
import stat

from linxira_recovery_diagnostics.collector import LOW_SPACE_BYTES, WORKSPACE_GUARD_CONF
from linxira_recovery_diagnostics.plans import PLAN_IDS, make_plan

STORE = "/var/lib/linxira/guard"
WORKSPACES = f"{STORE}/workspaces"
WORKSPACE_ID = "53270fff4fb72a9f-linxira-os"
SNAPSHOT = "20260926T041500Z-1a2b3c4d"


def guard_conf(store: str = STORE) -> str:
    return f"[guard]\nstore = {store}\nschedule = *:0/30\nkeep_scheduled = 24\nkeep_manual = 10\n"


def reader_with_guard(store_mode: int = 0o700, free: int | None = None):
    from conftest import FakeReader

    files = {
        WORKSPACE_GUARD_CONF: guard_conf(),
        f"{WORKSPACES}/{WORKSPACE_ID}/registered.json": json.dumps(
            {"workspace_id": WORKSPACE_ID, "workspace_path": "/home/user/Linxira-OS"}
        ),
        f"{WORKSPACES}/{WORKSPACE_ID}/{SNAPSHOT}/guard-manifest.json": json.dumps(
            {"schema": "org.linxira.components.guard-manifest.v1", "byte_size": 4096}
        ),
    }
    directories = {
        STORE: (),
        WORKSPACES: (WORKSPACE_ID,),
        f"{WORKSPACES}/{WORKSPACE_ID}": ("registered.json", SNAPSHOT),
        f"{WORKSPACES}/{WORKSPACE_ID}/{SNAPSHOT}": ("guard-manifest.json",),
    }
    return FakeReader(
        files=files, directories=directories,
        modes={STORE: stat.S_IFDIR | store_mode},
        free={STORE: free},
    )


def collect(reader):
    from conftest import FakeRunner
    from linxira_recovery_diagnostics.collector import EvidenceCollector

    return EvidenceCollector(reader=reader, runner=FakeRunner({})).collect()


def test_inventory_reports_unconfigured_store():
    from conftest import FakeReader

    report = collect(FakeReader())
    guard = report["workspace_guard"]
    assert guard["configured"] is False
    assert guard["store"] is None
    assert guard["store_present"] is False
    assert guard["workspaces"] == []
    assert guard["snapshot_count"] == 0
    assert guard["free_low"] is False


def test_inventory_reads_configured_store():
    report = collect(reader_with_guard(free=8 * 1024**3))
    guard = report["workspace_guard"]
    assert guard["configured"] is True
    assert guard["store"] == STORE
    assert guard["store_present"] is True
    assert guard["store_mode_ok"] is True
    assert guard["free_bytes"] == 8 * 1024**3
    assert guard["free_low"] is False
    assert len(guard["workspaces"]) == 1
    assert guard["workspaces"][0]["workspace_path"] == "/home/user/Linxira-OS"
    assert guard["snapshot_count"] == 1
    assert guard["total_bytes"] == 4096


def test_inventory_rejects_world_readable_store():
    report = collect(reader_with_guard(store_mode=0o755))
    guard = report["workspace_guard"]
    assert guard["store_mode_ok"] is False
    # 权限不对不影响读数, 只把它标出来交给计划与界面。
    assert guard["snapshot_count"] == 1


def test_inventory_flags_low_space():
    report = collect(reader_with_guard(free=LOW_SPACE_BYTES - 1))
    assert report["workspace_guard"]["free_low"] is True


def test_guard_plan_unavailable_reasons():
    from conftest import FakeReader

    unconfigured = collect(FakeReader())
    create = make_plan("org.linxira.guard.create-workspace-snapshot.v1", unconfigured)
    assert create["available"] is False
    assert "guard-store-not-configured" in create["unavailable_reasons"]
    assert "future-root-receipt-required" not in create["unavailable_reasons"]

    low = collect(reader_with_guard(free=LOW_SPACE_BYTES - 1))
    create = make_plan("org.linxira.guard.create-workspace-snapshot.v1", low)
    assert create["available"] is False
    assert "guard-space-low" in create["unavailable_reasons"]
    assert "guard-store-not-configured" not in create["unavailable_reasons"]

    restore = make_plan("org.linxira.guard.restore-workspace-snapshot.v1", unconfigured)
    assert restore["available"] is False
    assert "no-snapshots" in restore["unavailable_reasons"]
    assert "future-root-receipt-required" in restore["unavailable_reasons"]

    with_snapshots = collect(reader_with_guard())
    restore = make_plan("org.linxira.guard.restore-workspace-snapshot.v1", with_snapshots)
    assert "no-snapshots" not in restore["unavailable_reasons"]
    assert restore["available"] is False


def test_new_plans_registered():
    assert "org.linxira.guard.create-workspace-snapshot.v1" in PLAN_IDS
    assert "org.linxira.guard.restore-workspace-snapshot.v1" in PLAN_IDS
    assert len(PLAN_IDS) == 8
