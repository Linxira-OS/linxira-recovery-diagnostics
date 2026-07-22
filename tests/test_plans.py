from __future__ import annotations

from linxira_recovery_diagnostics.plans import PLAN_IDS, make_plan


def test_only_read_only_diagnostics_have_a_system_backend(make_collector):
    collector, _, _ = make_collector(live=True)
    report = collector.collect()
    assert len(PLAN_IDS) == 6
    available = set()
    for plan_id in PLAN_IDS:
        plan = make_plan(plan_id, report)
        assert plan["plan_id"] == plan_id
        if plan["available"]:
            available.add(plan_id)
            assert plan["apply"]["backend"] == "org.linxira.Components1"
            assert plan["apply"]["read_only"] is True
        else:
            assert plan["apply"]["backend"] == "not-ready"
        assert plan["effects"] and plan["preconditions"]
    assert available == {
        "org.linxira.recovery.pacman-lock-diagnose.v1",
        "org.linxira.recovery.live-chroot-readiness.v1",
    }


def test_rollback_never_accepts_snapshot_or_path(make_collector):
    collector, _, _ = make_collector()
    plan = make_plan("org.linxira.recovery.rollback.v1", collector.collect())
    assert "future-root-receipt-required" in plan["unavailable_reasons"]
    assert "snapshot_id" not in plan
    assert "path" not in plan


def test_snapshot_lock_and_keyring_preconditions_are_explicit(make_collector):
    collector, _, _ = make_collector()
    report = collector.collect()
    report["storage"]["space"] = [{"low": True}]
    report["pacman"]["lock"]["exists"] = True
    report["pacman"]["active_package_processes"] = [{"pid": 7, "program": "pacman"}]
    report["keyring"]["prerequisites"] = {
        "clock_sane": False,
        "network_interface_up": False,
        "default_ipv4_route": False,
    }
    snapshot = make_plan("org.linxira.snapshot.create-prechange.v1", report)
    lock = make_plan("org.linxira.recovery.pacman-lock-diagnose.v1", report)
    keyring = make_plan("org.linxira.recovery.keyring-repair.v1", report)
    assert "snapshot-space-low" in snapshot["unavailable_reasons"]
    assert lock["available"] is True
    assert lock["unavailable_reasons"] == []
    assert "system-clock-not-sane" in keyring["unavailable_reasons"]
    assert "network-route-unavailable" in keyring["unavailable_reasons"]
