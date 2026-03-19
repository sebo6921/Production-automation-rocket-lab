import logging
from client_registry import ClientRegistry
from discovery_manager import DiscoveryManager
from test_manager import TestManager

logger = logging.getLogger(__name__)


class DeviceController:
    # Shared across all tabs: "ip:port" strings of devices currently under test.
    # All mutations occur on the Qt main thread via queued signal delivery,
    # so no lock is required.
    _global_running: list = []

    def __init__(self, panel):
        self._registry = ClientRegistry()
        self._discovery = DiscoveryManager(panel, self._registry, DeviceController._global_running)
        self._tests = TestManager(panel, self._registry, DeviceController._global_running)
        self._panel = panel

    def on_discover(self) -> None:
        if self._is_busy():
            self._panel._warn("A test is running. Stop it before scanning.")
            return
        self._discovery.discover()

    def on_multicast_scan(self) -> None:
        if self._is_busy():
            self._panel._warn("A test is running. Stop it before scanning.")
            return
        self._discovery.multicast_scan()

    def on_start(self) -> None:
        self._tests.start()

    def on_stop(self) -> None:
        self._tests.stop()

    def cleanup(self) -> None:
        self._tests.cleanup()
        self._registry.close_all()

    def _is_busy(self) -> bool:
        return self._tests.is_running() or bool(DeviceController._global_running)