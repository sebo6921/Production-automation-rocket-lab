from device_client import DeviceClient

class ClientRegistry:
    """Stores discovered devices and manages DeviceClient creation.

    Devices are stored as plain dicts until a test starts — this defers
    socket creation and avoids competing with running test workers during scans.
    """

    def __init__(self):
        self._clients: dict = {}  # label -> dict (pre-test) or DeviceClient (post-start)

    def add(self, label: str, ip: str, port: int, model: str, serial: str) -> None:
        self._clients[label] = {"ip": ip, "port": port, "model": model, "serial": serial}

    def has_key(self, key: str) -> bool:
        """Return True if 'ip:port' is already registered."""
        return any(self.key_for(l) == key for l in self._clients)

    def key_for(self, label: str) -> str:
        """Return 'ip:port' for a label regardless of storage type."""
        c = self._clients[label]
        return f"{c['ip']}:{c['port']}" if isinstance(c, dict) else f"{c.ip}:{c.port}"

    def get_or_create(self, label: str) -> DeviceClient:
        """Return the DeviceClient, creating it from stored info if not yet created."""
        if isinstance(self._clients[label], dict):
            info = self._clients[label]
            client = DeviceClient(info["ip"], info["port"])
            client.model = info["model"]
            client.serial = info["serial"]
            self._clients[label] = client
        return self._clients[label]

    def get(self, label: str) -> DeviceClient:
        return self._clients[label]

    def close_all(self) -> None:
        for client in self._clients.values():
            if isinstance(client, DeviceClient):
                client.close()
        self._clients.clear()