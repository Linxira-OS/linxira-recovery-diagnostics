from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any


BUS_NAME = "org.linxira.Components1"
OBJECT_PATH = "/org/linxira/Components1"
INTERFACE = "org.linxira.Components1"
SYSTEM_OPERATION_IDS = frozenset({
    "org.linxira.recovery.pacman-lock-diagnose.v1",
    "org.linxira.recovery.live-chroot-readiness.v1",
})


class BackendError(RuntimeError):
    pass


@dataclass(frozen=True)
class Transaction:
    plan_id: str
    plan: dict[str, Any]


def _interface():
    try:
        import dbus
    except ImportError as exc:
        raise BackendError("The Linxira system D-Bus client is unavailable") from exc
    bus = dbus.SystemBus()
    proxy = bus.get_object(BUS_NAME, OBJECT_PATH)
    return dbus.Interface(proxy, INTERFACE)


def _document(value: str, description: str) -> dict[str, Any]:
    try:
        document = json.loads(value)
    except json.JSONDecodeError as exc:
        raise BackendError(f"System backend returned invalid {description}") from exc
    if not isinstance(document, dict):
        raise BackendError(f"System backend returned invalid {description}")
    return document


def create_plan(operation_id: str, interface=None) -> Transaction:
    if operation_id not in SYSTEM_OPERATION_IDS:
        raise BackendError("This recovery action has no executable system backend")
    client = _interface() if interface is None else interface
    try:
        plan_id, plan_json = client.CreateSystemPlan(operation_id, "{}", timeout=120)
    except Exception as exc:
        raise BackendError(str(exc)) from exc
    plan = _document(str(plan_json), "plan")
    if plan.get("id") != str(plan_id) or plan.get("operationId") != operation_id:
        raise BackendError("System backend returned a mismatched plan")
    if not isinstance(plan.get("digest"), str):
        raise BackendError("System backend plan has no digest")
    return Transaction(str(plan_id), plan)


def confirm_and_apply(transaction: Transaction, interface=None) -> dict[str, Any]:
    client = _interface() if interface is None else interface
    try:
        receipt_id, receipt_json = client.ConfirmAndApplySystemPlan(
            transaction.plan_id, transaction.plan["digest"], timeout=120
        )
    except Exception as exc:
        raise BackendError(str(exc)) from exc
    receipt = _document(str(receipt_json), "receipt")
    if receipt.get("id") != str(receipt_id) or receipt.get("planId") != transaction.plan_id:
        raise BackendError("System backend returned a mismatched receipt")
    if (
        receipt.get("planDigest") != transaction.plan.get("digest")
        or receipt.get("operationId") != transaction.plan.get("operationId")
    ):
        raise BackendError("System backend receipt does not match the confirmed operation")
    if receipt.get("status") != "succeeded" or receipt.get("changed") is not False:
        raise BackendError("Read-only recovery diagnostic did not complete safely")
    return receipt
