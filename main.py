import sys
import logging

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton,
    QHBoxLayout, QTabWidget, QVBoxLayout, QWidget,
)
from device_tab import DevicePanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rocket Lab — UDP Test")
        self.setMinimumWidth(900)
        self._tab_counter = 0

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 20, 0, 0)
        layout.setSpacing(10)

        # Header
        header = QHBoxLayout()
        header.addStretch()
        logo = QLabel()
        pixmap = QPixmap("image.png")
        logo.setPixmap(pixmap.scaled(400, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        header.addWidget(logo)
        header.addStretch()
        layout.addLayout(header)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.tabBar().setExpanding(False)
        self._tabs.tabCloseRequested.connect(self._close_tab)

        add_btn = QPushButton("+ Add Device")
        add_btn.clicked.connect(self._add_tab)
        self._tabs.setCornerWidget(add_btn, Qt.TopRightCorner)

        layout.addWidget(self._tabs, stretch=1)
        self._add_tab()

    def _add_tab(self):
        panel = DevicePanel()
        self._tab_counter += 1
        self._tabs.addTab(panel, f"Device {self._tab_counter}")

    def _close_tab(self, index):
        if self._tabs.count() == 1:
            return
        panel = self._tabs.widget(index)
        if hasattr(panel, "_controller"):
            panel._controller.cleanup()
        self._tabs.removeTab(index)


def main():
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()