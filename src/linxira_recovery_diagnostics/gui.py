from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPushButton, QTabWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from .collector import EvidenceCollector
from .plans import PLAN_IDS, make_plan
from .support import create_support_bundle, preview_manifest, save_plan


def _json_view(value: Any) -> QTextBrowser:
    view = QTextBrowser()
    view.setPlainText(json.dumps(value, indent=2, sort_keys=True))
    view.setFont(QFont("monospace"))
    return view


class MainWindow(QMainWindow):
    def __init__(self, report: dict[str, Any] | None = None):
        super().__init__()
        self.report = report if report is not None else EvidenceCollector().collect()
        self.setWindowTitle("Linxira Recovery Diagnostics")
        self.resize(980, 700)
        tabs = QTabWidget()
        tabs.addTab(self._overview(), "Overview")
        tabs.addTab(self._snapshots(), "Snapshots")
        tabs.addTab(self._repairs(), "Repairs")
        tabs.addTab(self._support(), "Support report")
        self.setCentralWidget(tabs)

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
        selector = QComboBox()
        selector.addItems(PLAN_IDS)
        details = _json_view(make_plan(selector.currentText(), self.report))
        selector.currentTextChanged.connect(lambda plan_id: details.setPlainText(json.dumps(make_plan(plan_id, self.report), indent=2, sort_keys=True)))
        layout.addWidget(selector)
        layout.addWidget(details)
        buttons = QHBoxLayout()
        save = QPushButton("Save plan")
        save.clicked.connect(lambda: self._save_plan(selector.currentText()))
        apply = QPushButton("Apply")
        apply.setEnabled(False)
        apply.setToolTip("Apply backend not ready")
        buttons.addWidget(save)
        buttons.addWidget(apply)
        buttons.addStretch()
        layout.addLayout(buttons)
        page.setLayout(layout)
        return page

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
