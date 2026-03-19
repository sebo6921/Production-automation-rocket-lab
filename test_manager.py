import logging
from device_worker import TestWorker
from Utils.qt_helper import _launch_worker
from colours import DEVICE_COLOURS

logger = logging.getLogger(__name__)

class TestManager:
    """Manages test lifecycle: start, stop, status updates, and teardown."""

    def __init__(self, panel, registry, global_running: list):
        self._panel = panel
        self._registry = registry
        self._global_running = global_running
        self._running: dict = {}   # label -> {"worker": ..., "thread": ...}
        self._colour_index = 0

    def is_running(self) -> bool:
        return bool(self._running)

    def start(self) -> None:
        checked = self._panel.get_checked_labels()
        if not checked:
            self._panel._warn("Please check at least one device.")
            return
        if any(label in self._running for label in checked):
            self._panel._warn("A test is already running. Stop it first.")
            return
        if any(self._registry.key_for(l) in self._global_running for l in checked):
            self._panel._warn("One or more devices are already being tested in another tab.\nStop that test first.")
            return

        duration = self._panel.duration_spin.value()
        rate = self._panel.rate_spin.value()
        if not (1 <= duration <= 10000):
            self._panel._warn("Duration must be between 1 and 10000.")
            return
        if not (1 <= rate <= 3600):
            self._panel._warn("Rate must be between 1 and 3600.")
            return

        self._panel.plot_widget.clear_all()
        self._colour_index = 0

        for label in checked:
            client = self._registry.get_or_create(label)
            client._clear_data()

            self._global_running.append(f"{client.ip}:{client.port}")

            mv_colour, ma_colour = DEVICE_COLOURS[self._colour_index % len(DEVICE_COLOURS)]
            self._colour_index += 1
            self._panel.plot_widget.add_series(label, mv_colour, ma_colour)

            worker = TestWorker(client, duration, rate)
            worker.finished.connect(lambda l=label: self._on_finished(l))
            worker.error.connect(lambda msg, l=label: self._on_error(msg, l))
            worker.status_update.connect(lambda t, mv, ma, l=label: self._on_status_update(t, mv, ma, l))

            self._running[label] = {"worker": worker, "thread": _launch_worker(worker)}
            self._panel.set_item_status(label, "running")

        self._panel.set_running_state(True)
        self._panel.status_label.setText(f"Running {len(self._running)} test(s)…")

    def stop(self) -> None:
        labels = self._panel.get_checked_labels() or list(self._running.keys())
        for label in labels:
            if label not in self._running:
                continue
            self._running[label]["worker"].stop()
            self._registry.get(label).stop_test()
            if self._running[label]["thread"].isRunning():
                self._running[label]["thread"].quit()
        self._panel.status_label.setText("Stopping…")

    def cleanup(self) -> None:
        for label, entry in list(self._running.items()):
            entry["worker"].stop()
            if entry["thread"].isRunning():
                entry["thread"].quit()
                entry["thread"].wait()
            key = self._registry.key_for(label)
            if key in self._global_running:
                self._global_running.remove(key)
        self._running.clear()

    def _on_status_update(self, time_ms, mv, ma, label: str) -> None:
        client = self._registry.get(label)
        self._panel.plot_widget.update_series(label, client.times, client.mvs, client.mas)

    def _teardown_test(self, label: str, status: str) -> None:
        entry = self._running.pop(label, None)
        if entry is None:
            return
        thread = entry["thread"]
        thread.quit()
        thread.wait()
        thread.deleteLater()

        key = self._registry.key_for(label)
        if key in self._global_running:
            self._global_running.remove(key)

        self._panel.set_item_status(label, status)
        if not self._running:
            self._panel.set_running_state(False)

    def _on_finished(self, label: str) -> None:
        self._teardown_test(label, "done")
        if not self._running:
            self._panel.status_label.setText("Status: all done")

    def _on_error(self, message: str, label: str) -> None:
        logger.error("Test error on %s: %s", label, message)
        self._panel.plot_widget.mark_series_inactive(label)
        self._teardown_test(label, "error")
        if not self._running:
            self._panel.status_label.setText(f"Error: {message}")