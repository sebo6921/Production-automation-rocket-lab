from PyQt5.QtCore import QObject, pyqtSignal
from  device_client import DeviceClient, DeviceError 
import time
import socket
from Utils.helpers import parse_message
class DiscoveryWorker(QObject):
    discovered = pyqtSignal(str, str, str, str)  # model, serial, ip, port
    failed = pyqtSignal(str)

    def __init__(self, ip: str, port: int):
        super().__init__()
        self._ip = ip
        self._port = port

    def run(self):
        client = None
        try:
            client = DeviceClient(self._ip, self._port)
            client.discover()
            reply = client.receive_once()
            if reply is None:
                self.failed.emit("No response — is the device running?")
                return
            client.handle_message(reply)
            self.discovered.emit(client.model, client.serial, self._ip, str(self._port))
        except (OSError, DeviceError) as e:
            self.failed.emit(str(e))
        finally:
            if client is not None:
                client.close()
class MulticastScanWorker(QObject):
    discovered = pyqtSignal(str, str, str, str)  # model, serial, ip, port
    failed = pyqtSignal(str)
    finished = pyqtSignal() 

    def __init__(self, ip="224.3.11.15", port=31115):
        super().__init__()
        self._ip = ip
        self._port = port
    def run(self):
        self._sock = None
        try:
            message = "ID;"
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.sendto(message.encode("latin-1"), (self._ip, self._port))
            deadline = time.monotonic() + 2.0 
            self._sock.settimeout(0.5)

            while time.monotonic() < deadline:
                try:
                    data, addr = self._sock.recvfrom(4096)
                    parsed = parse_message(data.decode("latin-1"))
                    if parsed.get("type") != "ID":
                        continue  # sometimes we get ? / ? responses cause of the approach — ignore those
                    model = parsed.get("MODEL") or "Unknown model"
                    serial = parsed.get("SERIAL") or "Unknown serial"
                    self.discovered.emit(model, serial, addr[0], str(addr[1]))
                except socket.timeout:
                    continue
        except OSError as e:
            self.failed.emit(str(e))
        finally:
            if self._sock is not None:
                self._sock.close()
            self.finished.emit()


class TestWorker(QObject):
    finished = pyqtSignal()
    status_update = pyqtSignal(float, float, float)  # time_ms, mv, ma
    error = pyqtSignal(str)

    def __init__(self, client: DeviceClient, duration: int, rate: int):
        super().__init__()
        self._client = client
        self._duration = duration
        self._rate = rate
        self._stop = False


    def run(self):
        try:
            self._client.start_test(self._duration, self._rate)
        except OSError as e:
            self.error.emit(str(e))
            return
        deadline = time.monotonic() + 5.0  # 5 second timeout to get confirmation
        while time.monotonic() < deadline:
            text = self._client.receive_once()
            if text is None:
                continue
            try:
                parsed = self._client.handle_message(text)
            except DeviceError as e:
                self.error.emit(str(e))
                return

            if parsed["type"] == "TEST":
                if parsed.get("RESULT") == "STARTED":
                    break 
                elif parsed.get("RESULT") == "ERROR":
                    return
        else:
            self.error.emit("Timed out waiting for test to start.")
            return

        deadline = time.monotonic() + self._duration + 5
        while time.monotonic() < deadline and not self._stop:
            text = self._client.receive_once()
            if text is None:
                continue
            try:
                parsed = self._client.handle_message(text)
            except DeviceError as e:
                self.error.emit(str(e))
                return
            if parsed["type"] == "TEST":
                if parsed.get("RESULT") == "STOPPED":
                    self.finished.emit()
                    return
            elif parsed["type"] == "STATUS":
                if parsed.get("STATE") == "IDLE":
                    self.finished.emit()
                    return
                if self._client.times:
                    self.status_update.emit(
                        self._client.times[-1],
                        self._client.mvs[-1],
                        self._client.mas[-1],
                    )

        self.finished.emit()

    def stop(self):
        self._stop = True