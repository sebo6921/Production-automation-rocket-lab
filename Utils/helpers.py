from typing import Dict, Any
import logging
logger = logging.getLogger(__name__)

def valid_port(port_str: str) -> bool:
    if not port_str.isdigit():
        return False
    port = int(port_str)
    return 1 <= port <= 65535

def valid_ip(ip_str: str) -> bool:
    parts = ip_str.split(".")
    if len(parts) != 4:
        return False
    for part in parts:
        if not part.isdigit():
            return False
        num = int(part)
        if not (0 <= num <= 255):
            return False
    return True

def parse_message(text: str) -> Dict[str, Any]:
    parts = [p for p in text.strip().split(";") if p]
    if not parts:
        return {"type": "UNKNOWN"}

    parsed: Dict[str, Any] = {"type": parts[0]}
    for part in parts[1:]:
        if "=" in part:
            key, value = part.split("=", 1)
            parsed[key] = value
        else:
            logger.debug("Ignoring token with no '=': %r", part)

    return parsed


