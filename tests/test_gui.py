from __future__ import annotations

import os
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton, QTabWidget

from linxira_recovery_diagnostics.gui import MainWindow


def test_qt_smoke(make_collector, monkeypatch):
    app = QApplication.instance() or QApplication([])
    collector, _, _ = make_collector(live=True)
    window = MainWindow(collector.collect())
    tabs = window.findChild(QTabWidget)
    assert [tabs.tabText(index) for index in range(tabs.count())] == ["Overview", "Snapshots", "Repairs", "Support report"]
    apply_buttons = [button for button in window.findChildren(QPushButton) if button.text() == "Run diagnostic"]
    assert len(apply_buttons) == 1
    assert apply_buttons[0].isEnabled() is False
    window.repair_selector.setCurrentText("org.linxira.recovery.pacman-lock-diagnose.v1")
    assert apply_buttons[0].isEnabled() is True
    saved = []
    monkeypatch.setattr(window, "_save_plan", saved.append)
    next(button for button in window.findChildren(QPushButton) if button.text() == "Save plan").click()
    assert saved == ["org.linxira.recovery.pacman-lock-diagnose.v1"]
    window.close()
    app.processEvents()


def test_close_is_deferred_while_backend_worker_runs(make_collector, monkeypatch):
    app = QApplication.instance() or QApplication([])
    collector, _, _ = make_collector(live=True)
    window = MainWindow(collector.collect())
    window.plan_worker = type("Worker", (), {"isRunning": lambda self: True})()
    event = type("Event", (), {"ignore": mock.Mock()})()
    monkeypatch.setattr("linxira_recovery_diagnostics.gui.QMessageBox.information", mock.Mock())
    window.closeEvent(event)
    event.ignore.assert_called_once()
    window.plan_worker = None
    window.close()
    app.processEvents()
