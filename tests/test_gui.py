from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton, QTabWidget

from linxira_recovery_diagnostics.gui import MainWindow


def test_qt_smoke(make_collector):
    app = QApplication.instance() or QApplication([])
    collector, _, _ = make_collector(live=True)
    window = MainWindow(collector.collect())
    tabs = window.findChild(QTabWidget)
    assert [tabs.tabText(index) for index in range(tabs.count())] == ["Overview", "Snapshots", "Repairs", "Support report"]
    apply_buttons = [button for button in window.findChildren(QPushButton) if button.text() == "Apply"]
    assert len(apply_buttons) == 1
    assert apply_buttons[0].isEnabled() is False
    window.close()
    app.processEvents()
