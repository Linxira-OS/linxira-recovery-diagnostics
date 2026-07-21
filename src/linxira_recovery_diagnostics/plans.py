from __future__ import annotations

from copy import deepcopy
from typing import Any

PLAN_SCHEMA = "org.linxira.recovery-diagnostics.plan"

_PLANS: dict[str, dict[str, Any]] = {
    "org.linxira.snapshot.create-prechange.v1": {
        "title": "Create a pre-change snapshot",
        "effects": ["Create one Timeshift snapshot using the configured backend.", "Record snapshot metadata for a future privileged recovery transaction."],
        "preconditions": ["A future trusted root-helper receipt authorizes this exact plan.", "Timeshift is installed and configured.", "The snapshot filesystem has sufficient free space."],
    },
    "org.linxira.recovery.rollback.v1": {
        "title": "Roll back from a trusted recovery receipt",
        "effects": ["Restore the snapshot named only by a future trusted root-helper receipt.", "Regenerate required boot artifacts after restore."],
        "preconditions": ["A future trusted root-helper receipt supplies and authorizes the snapshot identity.", "The receipt matches the current machine and report.", "The selected snapshot remains available."],
        "receipt_required": True,
    },
    "org.linxira.recovery.pacman-lock-diagnose.v1": {
        "title": "Diagnose the pacman database lock",
        "effects": ["Recheck the fixed pacman lock path and package-manager process state.", "Report whether administrator investigation is needed; do not delete the lock."],
        "preconditions": ["The lock still exists.", "No package-manager process may be disrupted."],
    },
    "org.linxira.recovery.keyring-repair.v1": {
        "title": "Repair package-signing keyring",
        "effects": ["Refresh the Arch Linux keyring through a future privileged backend.", "Verify package database signatures after refresh."],
        "preconditions": ["System clock is correct.", "A working network route is available.", "A future trusted root-helper receipt authorizes this exact plan."],
    },
    "org.linxira.recovery.initramfs-repair.v1": {
        "title": "Regenerate initramfs and GRUB configuration",
        "effects": ["Regenerate installed kernel initramfs images.", "Regenerate the GRUB configuration when GRUB is installed."],
        "preconditions": ["The intended root filesystem is identified.", "Boot and EFI filesystems required by the installation are mounted.", "A future trusted root-helper receipt authorizes this exact plan."],
    },
    "org.linxira.recovery.live-chroot-readiness.v1": {
        "title": "Prepare the fixed live recovery target",
        "effects": ["Recheck that the installed target at /mnt has required filesystems and tools.", "Report missing prerequisites for a future recovery backend."],
        "preconditions": ["The application is running in a recognized Linxira or Arch live environment.", "The installed root is mounted at the fixed target /mnt."],
    },
}

PLAN_IDS = tuple(_PLANS)


def make_plan(plan_id: str, report: dict[str, Any]) -> dict[str, Any]:
    if plan_id not in _PLANS:
        raise ValueError("unknown plan ID")
    definition = deepcopy(_PLANS[plan_id])
    reasons = ["apply-backend-not-ready"]
    if definition.pop("receipt_required", False):
        reasons.append("future-root-receipt-required")
    if plan_id == "org.linxira.snapshot.create-prechange.v1":
        if not report.get("snapshots", {}).get("timeshift", {}).get("installed"):
            reasons.append("timeshift-not-installed")
        if not report.get("storage", {}).get("btrfs", {}).get("detected"):
            reasons.append("btrfs-not-detected")
        if any(item.get("low") for item in report.get("storage", {}).get("space", [])):
            reasons.append("snapshot-space-low")
    if plan_id == "org.linxira.recovery.pacman-lock-diagnose.v1":
        pacman = report.get("pacman", {})
        if not pacman.get("lock", {}).get("exists"):
            reasons.append("pacman-lock-not-present")
        if pacman.get("active_package_processes"):
            reasons.append("package-manager-active")
    if plan_id == "org.linxira.recovery.keyring-repair.v1":
        prerequisites = report.get("keyring", {}).get("prerequisites", {})
        if not prerequisites.get("clock_sane"):
            reasons.append("system-clock-not-sane")
        if not prerequisites.get("network_interface_up") or not prerequisites.get("default_ipv4_route"):
            reasons.append("network-route-unavailable")
    if plan_id == "org.linxira.recovery.live-chroot-readiness.v1" and not report.get("installed_target", {}).get("ready"):
        reasons.append("fixed-live-target-not-ready")
    return {
        "schema": PLAN_SCHEMA, "schema_version": 1, "plan_id": plan_id,
        **definition, "available": False, "unavailable_reasons": reasons,
        "apply": {"backend": "not-ready", "accepts_user_input": False},
    }
