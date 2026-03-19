import socket
import time
import logging
from typing import Optional, Dict, Any
from enum import Enum, auto
from Utils.helpers import parse_message as _parse_message

logger = logging.getLogger(__name__)

class DeviceError(Exception):
    pass

class DeviceState(Enum):
    DISCONNECTED = auto()
    IDLE = auto()
    RUNNING = auto()
    ERROR = auto()


class DeviceClient:
    def __init__(self, ip: str, port: int, timeout: float = 2.0):
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.model: Optional[str] = None
        self.serial: Optional[str] = None
        self.state = DeviceState.DISCONNECTED
        self.last_error: Optional[str] = None
        self.times: list = []
        self.mvs: list = []
        self.mas: list = []
        self._sock: Optional[socket.socket] = None
        self._open_socket()

    def _open_socket(self) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("0.0.0.0", 0))
            sock.settimeout(self.timeout)
            self._sock = sock
            self.state = DeviceState.IDLE
            logger.debug("Socket opened for %s:%d", self.ip, self.port)
        except OSError as e:
            self.state = DeviceState.DISCONNECTED
            raise OSError(f"Failed to open socket for {self.ip}:{self.port}: {e}") from e

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            finally:
                self._sock = None
                self.state = DeviceState.DISCONNECTED
                logger.debug("Socket closed for %s:%d", self.ip, self.port)

    def send_command(self, message: str) -> None:
        if self._sock is None:
            raise OSError("Socket is not open.")
        try:
            self._sock.sendto(message.encode("latin-1"), (self.ip, self.port))
            logger.debug("Sent to %s:%d → %r", self.ip, self.port, message)
        except OSError as e:
            self.state = DeviceState.DISCONNECTED
            raise OSError(f"Failed to send to {self.ip}:{self.port}: {e}") from e

    def discover(self) -> None:
        self.send_command("ID;")

    def start_test(self, duration: int, rate: int) -> None:
        if duration <= 0:
            raise ValueError(f"duration must be > 0, got {duration}")
        if rate <= 0:
            raise ValueError(f"rate must be > 0, got {rate}")
        self.send_command(f"TEST;CMD=START;DURATION={duration};RATE={rate};")

    def stop_test(self) -> None:
        self.send_command("TEST;CMD=STOP;")

    def receive_once(self) -> Optional[str]:
        """Wait up to timeout seconds for one UDP packet from this device. Returns None on timeout."""
        if self._sock is None:
            raise OSError("Socket is not open.")

        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            self._sock.settimeout(remaining)
            try:
                data, addr = self._sock.recvfrom(4096)
            except socket.timeout:
                return None
            except OSError as e:
                self.state = DeviceState.DISCONNECTED
                raise OSError(f"Socket receive error: {e}") from e

            if addr[0] != self.ip or addr[1] != self.port:
                logger.warning("Ignored packet from %s:%s (expected %s:%s)", addr[0], addr[1], self.ip, self.port)
                continue

            text = data.decode("latin-1")
            logger.debug("Received from %s:%d ← %r", addr[0], addr[1], text)
            return text

    def handle_message(self, text: str) -> Dict[str, Any]:
        """Parse a message, update state, and return the parsed dict. Raises DeviceError on device errors."""
        parsed = _parse_message(text)
        msg_type = parsed["type"]

        if msg_type == "ID":
            self.model = parsed.get("MODEL")
            self.serial = parsed.get("SERIAL")
            logger.info("Device identified: model=%s serial=%s", self.model, self.serial)

        elif msg_type == "TEST":
            result = parsed.get("RESULT", "")
            if result == "STARTED":
                self.state = DeviceState.RUNNING
                self.last_error = None
                self.clear_data()
                logger.info("Test started on %s:%d", self.ip, self.port)
            elif result == "STOPPED":
                self.state = DeviceState.IDLE
                logger.info("Test stopped on %s:%d", self.ip, self.port)
            elif result == "ERROR":
                msg = parsed.get("MSG", "Unknown error")
                self.last_error = msg
                self.state = DeviceState.ERROR
                logger.error("Device error on %s:%d: %s", self.ip, self.port, msg)
                raise DeviceError(msg)
            else:
                logger.warning("Unrecognised TEST result: %r", result)

        elif msg_type == "STATUS":
            if parsed.get("STATE") == "IDLE":
                self.state = DeviceState.IDLE
                logger.info("Test finished (device idle) on %s:%d", self.ip, self.port)
            else:
                self.state = DeviceState.RUNNING
                try:
                    self.times.append(float(parsed["TIME"]))
                    self.mvs.append(float(parsed["MV"]))
                    self.mas.append(float(parsed["MA"]))
                except (KeyError, ValueError) as e:
                    logger.warning("Malformed STATUS payload (%s): %r", e, text)
        else:
            logger.warning("Unknown message type %r from %s:%d", msg_type, self.ip, self.port)

        return parsed

    def clear_data(self) -> None:
        self.times.clear()
        self.mvs.clear()
        self.mas.clear()