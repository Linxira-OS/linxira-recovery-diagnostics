from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout,
    QLabel, QMainWindow, QMessageBox, QPushButton, QTabWidget, QTextBrowser,
    QVBoxLayout, QWidget,
)

from .backend import Transaction, confirm_and_apply, create_plan
from .collector import EvidenceCollector
from .plans import PLAN_IDS, make_plan
from .support import create_support_bundle, preview_manifest, save_plan


def _json_view(value: Any) -> QTextBrowser:
    view = QTextBrowser()
    view.setPlainText(json.dumps(value, indent=2, sort_keys=True))
    view.setFont(QFont("monospace"))
    return view


class PlanThread(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, operation_id, parent=None):
        super().__init__(parent)
        self.operation_id = operation_id

    def run(self):
        try:
            self.succeeded.emit(create_plan(self.operation_id))
        except Exception as error:
            self.failed.emit(str(error))


class ApplyThread(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, transaction, parent=None):
        super().__init__(parent)
        self.transaction = transaction

    def run(self):
        try:
            self.succeeded.emit(confirm_and_apply(self.transaction))
        except Exception as error:
            self.failed.emit(str(error))


class PlanDialog(QDialog):
    def __init__(self, transaction, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Confirm read-only recovery diagnostic")
        self.resize(720, 560)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Review the complete root-owned plan before running it."))
        layout.addWidget(_json_view(transaction.plan), 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Confirm and run")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class MainWindow(QMainWindow):
    def __init__(self, report: dict[str, Any] | None = None):
        super().__init__()
        self.report = report if report is not None else EvidenceCollector().collect()
        self.plan_worker = None
        self.apply_worker = None
        self.setWindowTitle("Linxira Recovery Diagnostics")
        self.resize(980, 700)
        tabs = QTabWidget()
        tabs.addTab(self._overview(), "Overview")
        tabs.addTab(self._snapshots(), "Snapshots")
        tabs.addTab(self._repairs(), "Repairs")
        tabs.addTab(self._support(), "Support report")
        self.setCentralWidget(tabs)

    def closeEvent(self, event):
        workers = (self.plan_worker, self.apply_worker)
        if any(worker is not None and worker.isRunning() for worker in workers):
            event.ignore()
            QMessageBox.information(
                self, "Linxira Recovery Diagnostics",
                "Wait for the system diagnostic to finish before closing.",
            )
            return
        super().closeEvent(event)

    def _overview(self) -> QWidget:
        page, layout = QWidget(), QVBoxLayout()
        mode = "Live system" if self.report["mode"]["live"] else "Installed system"
        heading = QLabel(mode)
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        layout.addWidget(_json_view({key: self.report[key] for key in ("mounts", "storage", "pacman", "keyring", "boot", "installed_target", "warnings")}))
        page.setLayout(layout)
        return page

    def _snapshots(self) -> QWidget:
        page, layout = QWidget(), QVBoxLayout()
        title = QLabel("Snapshot evidence")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        layout.addWidget(_json_view(self.report["snapshots"]))
        page.setLayout(layout)
        return page

    def _repairs(self) -> QWidget:
        page, layout = QWidget(), QVBoxLayout()
        title = QLabel("Repair plans")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        self.repair_selector = QComboBox()
        self.repair_selector.addItems(PLAN_IDS)
        self.repair_details = _json_view(make_plan(self.repair_selector.currentText(), self.report))
        self.repair_selector.currentTextChanged.connect(self._repair_changed)
        layout.addWidget(self.repair_selector)
        layout.addWidget(self.repair_details)
        buttons = QHBoxLayout()
        save = QPushButton("Save plan")
        save.clicked.connect(lambda: self._save_plan(self.repair_selector.currentText()))
        self.apply_button = QPushButton("Run diagnostic")
        self.apply_button.clicked.connect(self._create_system_plan)
        buttons.addWidget(save)
        buttons.addWidget(self.apply_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        self._repair_changed(self.repair_selector.currentText())
        page.setLayout(layout)
        return page

    def _repair_changed(self, plan_id):
        plan = make_plan(plan_id, self.report)
        self.repair_details.setPlainText(json.dumps(plan, indent=2, sort_keys=True))
        busy = self.plan_worker is not None or self.apply_worker is not None
        self.apply_button.setEnabled(plan["available"] and not busy)
        self.apply_button.setToolTip(
            "" if plan["available"] else "This action remains unavailable until its fixed backend is complete"
        )

    def _create_system_plan(self):
        self.apply_button.setEnabled(False)
        self.plan_worker = PlanThread(self.repair_selector.currentText(), self)
        self.plan_worker.succeeded.connect(self._plan_ready)
        self.plan_worker.failed.connect(self._backend_failed)
        self.plan_worker.finished.connect(self._plan_finished)
        self.plan_worker.start()

    def _plan_ready(self, transaction: Transaction):
        if PlanDialog(transaction, self).exec() != QDialog.DialogCode.Accepted:
            self._repair_changed(self.repair_selector.currentText())
            return
        self.apply_worker = ApplyThread(transaction, self)
        self.apply_worker.succeeded.connect(self._receipt_ready)
        self.apply_worker.failed.connect(self._backend_failed)
        self.apply_worker.finished.connect(self._apply_finished)
        self.apply_worker.start()

    def _receipt_ready(self, receipt):
        self.report = EvidenceCollector().collect()
        self._repair_changed(self.repair_selector.currentText())
        QMessageBox.information(
            self, "Diagnostic complete", json.dumps(receipt, indent=2, sort_keys=True)
        )

    def _backend_failed(self, message):
        QMessageBox.critical(self, "System diagnostic failed", message)

    def _plan_finished(self):
        self.plan_worker.deleteLater()
        self.plan_worker = None
        self._repair_changed(self.repair_selector.currentText())

    def _apply_finished(self):
        self.apply_worker.deleteLater()
        self.apply_worker = None
        self._repair_changed(self.repair_selector.currentText())

    def _support(self) -> QWidget:
        page, layout = QWidget(), QVBoxLayout()
        title = QLabel("Support bundle preview")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        layout.addWidget(_json_view(preview_manifest(self.report)))
        create = QPushButton("Save private support bundle")
        create.clicked.connect(self._save_bundle)
        layout.addWidget(create, alignment=Qt.AlignmentFlag.AlignLeft)
        page.setLayout(layout)
        return page

    def _save_plan(self, plan_id: str) -> None:
        try:
            path = save_plan(make_plan(plan_id, self.report))
            QMessageBox.information(self, "Plan saved", str(path))
        except (OSError, RuntimeError) as error:
            QMessageBox.critical(self, "Could not save plan", str(error))

    def _save_bundle(self) -> None:
        try:
            path, _ = create_support_bundle(self.report)
            QMessageBox.information(self, "Support bundle saved", str(path))
        except (OSError, RuntimeError) as error:
            QMessageBox.critical(self, "Could not save support bundle", str(error))


def main(argv: Sequence[str] | None = None) -> int:
    app = QApplication(list(argv) if argv is not None else sys.argv)
    app.setApplicationName("Linxira Recovery Diagnostics")
    app.setStyleSheet("""
        QMainWindow { background: #f4f5f7; }
        QTabWidget::pane { border: 1px solid #c7cbd1; background: white; }
        QTabBar::tab { padding: 10px 18px; }
        QTabBar::tab:selected { color: #006b52; border-bottom: 3px solid #008a69; }
        QLabel#pageTitle { font-size: 20px; font-weight: 600; color: #20242a; padding: 8px 0; }
        QTextBrowser { border: 1px solid #d7dade; background: #fbfbfc; padding: 8px; }
        QPushButton { min-height: 30px; padding: 0 12px; }
        QPushButton:enabled { background: #007a5e; color: white; border: 1px solid #00644d; }
        QPushButton:disabled { color: #777; }
        QComboBox { min-height: 30px; padding: 0 8px; }
    """)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
