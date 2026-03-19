from PyQt5.QtWidgets import (
    QWidget, QGroupBox, QMessageBox,
    QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSpinBox, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt
from device_controller import DeviceController
from live_plot import LivePlot

class DevicePanel(QWidget):
    def __init__(self):
        super().__init__()
        self._controller = DeviceController(self)
        self._is_running = False
        self._is_discovering = False

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        layout.addWidget(self._build_connection_group())
        layout.addLayout(self._build_middle_row())
        layout.addWidget(self._build_plot(), stretch=1)
        layout.addWidget(self._build_status())

    #UI
    def _build_connection_group(self) -> QGroupBox:
        group = QGroupBox("Connection")
        row = QHBoxLayout()

        row.addWidget(QLabel("IP:"))
        self.ip_edit = QLineEdit()
        row.addWidget(self.ip_edit)

        row.addWidget(QLabel("Port:"))
        self.port_edit = QLineEdit()
        self.port_edit.setFixedWidth(70)
        row.addWidget(self.port_edit)

        self.discover_btn = QPushButton("Discover")
        self.discover_btn.clicked.connect(self._controller.on_discover)
        row.addWidget(self.discover_btn)

        self.multi_discovery = QPushButton("Multicast Scan")
        self.multi_discovery.clicked.connect(self._controller.on_multicast_scan)
        row.addWidget(self.multi_discovery)

        group.setLayout(row)
        return group

    def _build_middle_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(self._build_device_list())
        row.addWidget(self._build_test_controls())
        return row

    def _build_device_list(self) -> QGroupBox:
        group = QGroupBox("Discovered Devices")
        layout = QVBoxLayout()
        self.discovery_widget = QListWidget()
        self.discovery_widget.setSelectionMode(QListWidget.NoSelection)
        self.discovery_widget.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.discovery_widget)
        group.setLayout(layout)
        return group

    def _build_test_controls(self) -> QGroupBox:
        group = QGroupBox("Test Controls")
        layout = QVBoxLayout()

        dur_row = QHBoxLayout()
        dur_row.addWidget(QLabel("Duration (s):"))
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(1, 3600)
        self.duration_spin.setValue(10)
        dur_row.addWidget(self.duration_spin)
        dur_row.addStretch()
        layout.addLayout(dur_row)

        rate_row = QHBoxLayout()
        rate_row.addWidget(QLabel("Rate (ms):"))
        self.rate_spin = QSpinBox()
        self.rate_spin.setRange(1, 10000)
        self.rate_spin.setValue(1000)
        rate_row.addWidget(self.rate_spin)
        rate_row.addStretch()
        layout.addLayout(rate_row)

        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("Start Test")
        self.start_btn.setEnabled(False)
        self.start_btn.setToolTip("Check at least one device first")
        self.start_btn.clicked.connect(self._controller.on_start)
        btn_row.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._controller.on_stop)
        btn_row.addWidget(self.stop_btn)

        layout.addLayout(btn_row)
        layout.addStretch()
        group.setLayout(layout)
        return group

    def _build_plot(self) -> "LivePlot":
        self.plot_widget = LivePlot()
        self.plot_widget.setMinimumHeight(250)
        return self.plot_widget

    def _build_status(self) -> QLabel:
        self.status_label = QLabel("Status: idle")
        self.status_label.setAlignment(Qt.AlignCenter)
        return self.status_label

    def add_device_item(self, label: str):
        item = QListWidgetItem(label)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Unchecked)
        self.discovery_widget.addItem(item)

    def get_checked_labels(self) -> list:
        return [
            self.discovery_widget.item(i).text().split(" [")[0]
            for i in range(self.discovery_widget.count())
            if self.discovery_widget.item(i).checkState() == Qt.Checked
        ]

    def set_item_status(self, label: str, status: str):
        for i in range(self.discovery_widget.count()):
            item = self.discovery_widget.item(i)
            if item.text().split(" [")[0] == label:
                item.setText(f"{label} [{status}]")
                break

    def set_running_state(self, is_running: bool):
        self._is_running = is_running
        self._refresh_button_states()

    def set_discovering_state(self, is_discovering: bool):
        self._is_discovering = is_discovering
        self._refresh_button_states()

    def _on_item_changed(self, _item):
        self._refresh_button_states()

    def _refresh_button_states(self):
        any_checked = any(
            self.discovery_widget.item(i).checkState() == Qt.Checked
            for i in range(self.discovery_widget.count())
        )
        self.start_btn.setEnabled(any_checked and not self._is_running)
        self.stop_btn.setEnabled(self._is_running)
        self.discover_btn.setEnabled(not self._is_discovering)
        self.multi_discovery.setEnabled(not self._is_discovering)

    def _warn(self, msg: str):
        QMessageBox.warning(self, "Warning", msg)