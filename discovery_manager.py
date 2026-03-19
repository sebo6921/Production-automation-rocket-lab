import logging
from device_worker import DiscoveryWorker, MulticastScanWorker
from Utils.helpers import valid_ip, valid_port
from Utils.qt_helper import _launch_worker

logger = logging.getLogger(__name__)


class DiscoveryManager:
    """Handles unicast and multicast device discovery."""

    def __init__(self, panel, registry, global_running: list):
        self._panel = panel
        self._registry = registry
        self._global_running = global_running
        self._discovery_worker = None
        self._discovery_thread = None
        self._multicast_worker = None
        self._multicast_thread = None
        self._new_devices_found = 0

    def is_scanning(self) -> bool:
        return (
            (self._discovery_thread is not None and self._discovery_thread.isRunning()) or
            (self._multicast_thread is not None and self._multicast_thread.isRunning())
        )

    def discover(self) -> None:
        ip = self._panel.ip_edit.text().strip()
        port = self._panel.port_edit.text().strip()
        if not valid_ip(ip):
            self._panel._warn("Please enter a valid IP address.")
            return
        if not valid_port(port):
            self._panel._warn("Please enter a valid port number (1-65535).")
            return
        if self._discovery_thread is not None and self._discovery_thread.isRunning():
            return

        self._discovery_worker = DiscoveryWorker(ip, int(port))
        self._discovery_worker.discovered.connect(self._on_discovered)
        self._discovery_worker.failed.connect(self._on_failed)
        self._discovery_thread = _launch_worker(
            self._discovery_worker,
            self._discovery_worker.discovered,
            self._discovery_worker.failed,
        )
        self._discovery_thread.finished.connect(
            lambda: self._panel.set_discovering_state(False)
        )
        self._panel.set_discovering_state(True)
        self._panel.status_label.setText("Searching…")

    def multicast_scan(self) -> None:
        if self.is_scanning():
            return

        self._new_devices_found = 0
        self._multicast_worker = MulticastScanWorker()
        self._multicast_worker.discovered.connect(self._on_discovered)
        self._multicast_worker.failed.connect(self._on_failed)
        self._multicast_worker.finished.connect(self._on_multicast_finished)
        self._multicast_thread = _launch_worker(
            self._multicast_worker,
            self._multicast_worker.failed,
            self._multicast_worker.finished,
        )
        self._panel.set_discovering_state(True)
        self._panel.status_label.setText("Scanning for devices…")

    def _on_discovered(self, model: str, serial: str, ip: str, port: str) -> None:
        key = f"{ip}:{port}"

        if self._registry.has_key(key):
            logger.warning("Device already found at %s", key)
            self._panel.status_label.setText(f"Found: {model} / {serial} — already in list")
            return

        if key in self._global_running:
            logger.warning("Skipping %s — currently under test in another tab", key)
            self._panel.status_label.setText(f"Found: {model} / {serial} — busy in another tab")
            return

        self._new_devices_found += 1
        label = f"{model} / {serial} — {ip}:{port}"
        self._registry.add(label, ip, int(port), model, serial)
        self._panel.add_device_item(label)
        self._panel.status_label.setText(f"Found: {model} / {serial}")

    def _on_failed(self, message: str) -> None:
        logger.error("Discovery failed: %s", message)
        self._panel.status_label.setText(f"Error: {message}")
        self._panel.set_discovering_state(False)

    def _on_multicast_finished(self) -> None:
        self._panel.set_discovering_state(False)
        self._panel.status_label.setText(
            f"Scan complete — {self._new_devices_found} new device(s) found"
        )