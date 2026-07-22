from __future__ import annotations

import json
from unittest import mock

import pytest

from linxira_recovery_diagnostics.backend import (
    BackendError,
    confirm_and_apply,
    create_plan,
)


OPERATION = "org.linxira.recovery.pacman-lock-diagnose.v1"


def test_backend_uses_only_fixed_bus_operation_and_empty_parameters():
    interface = mock.Mock()
    interface.CreateSystemPlan.return_value = (
        "plan-id",
        json.dumps({"id": "plan-id", "operationId": OPERATION, "digest": "digest"}),
    )
    transaction = create_plan(OPERATION, interface)
    assert transaction.plan_id == "plan-id"
    interface.CreateSystemPlan.assert_called_once_with(OPERATION, "{}", timeout=120)


def test_backend_rejects_unknown_operation_before_dbus():
    interface = mock.Mock()
    with pytest.raises(BackendError, match="no executable"):
        create_plan("org.linxira.recovery.rollback.v1", interface)
    interface.assert_not_called()


def test_backend_confirms_digest_and_requires_read_only_success_receipt():
    interface = mock.Mock()
    interface.ConfirmAndApplySystemPlan.return_value = (
        "receipt-id",
        json.dumps({
            "id": "receipt-id", "planId": "plan-id", "status": "succeeded",
            "changed": False, "planDigest": "digest", "operationId": OPERATION,
        }),
    )
    transaction = create_plan(
        OPERATION,
        mock.Mock(CreateSystemPlan=mock.Mock(return_value=(
            "plan-id", json.dumps({"id": "plan-id", "operationId": OPERATION, "digest": "digest"})
        ))),
    )
    receipt = confirm_and_apply(transaction, interface)
    assert receipt["id"] == "receipt-id"
    interface.ConfirmAndApplySystemPlan.assert_called_once_with(
        "plan-id", "digest", timeout=120
    )


def test_backend_rejects_receipt_for_another_operation():
    transaction = create_plan(
        OPERATION,
        mock.Mock(CreateSystemPlan=mock.Mock(return_value=(
            "plan-id", json.dumps({"id": "plan-id", "operationId": OPERATION, "digest": "digest"})
        ))),
    )
    interface = mock.Mock()
    interface.ConfirmAndApplySystemPlan.return_value = (
        "receipt-id",
        json.dumps({
            "id": "receipt-id", "planId": "plan-id", "status": "succeeded",
            "changed": False, "planDigest": "digest", "operationId": "other",
        }),
    )
    with pytest.raises(BackendError, match="confirmed operation"):
        confirm_and_apply(transaction, interface)


def test_backend_rejects_receipt_for_another_plan_digest():
    transaction = create_plan(
        OPERATION,
        mock.Mock(CreateSystemPlan=mock.Mock(return_value=(
            "plan-id", json.dumps({"id": "plan-id", "operationId": OPERATION, "digest": "digest"})
        ))),
    )
    interface = mock.Mock()
    interface.ConfirmAndApplySystemPlan.return_value = (
        "receipt-id",
        json.dumps({
            "id": "receipt-id", "planId": "plan-id", "status": "succeeded",
            "changed": False, "planDigest": "other", "operationId": OPERATION,
        }),
    )
    with pytest.raises(BackendError, match="confirmed operation"):
        confirm_and_apply(transaction, interface)
