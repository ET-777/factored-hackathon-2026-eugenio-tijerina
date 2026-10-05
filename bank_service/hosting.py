"""Explicit public fictional-demo configuration for a trusted TLS boundary.

This config selects a fixed authority at startup. Request Forwarded and
X-Forwarded-* headers cannot change that authority or establish HTTPS.
The listener itself is HTTP and must sit behind a trusted HTTPS terminator.
"""

from dataclasses import dataclass
import ipaddress
import re
from urllib.parse import urlsplit


_AUTHORITY = re.compile(r"([a-z0-9.-]+)(?::([1-9][0-9]{0,4}))?\Z", re.ASCII)
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z", re.ASCII)


@dataclass(frozen=True)
class HostingConfig:
    """Opt-in HTTP bind plus one canonical external HTTPS origin.

    DNS names are ASCII lowercase, with at least two labels and no trailing
    dot. Default HTTPS port 443 is omitted; a nondefault port is allowed.
    Bind values are deliberate literals, never externally resolved names.
    """

    public_origin: str
    bind_host: str = "0.0.0.0"

    def __post_init__(self) -> None:
        invalid = ValueError("invalid_hosting_config")
        origin = self.public_origin
        if (not isinstance(origin, str) or not origin.isascii()
                or origin != origin.strip() or not origin
                or any(ord(char) < 33 or ord(char) == 127 for char in origin)
                or "\\" in origin
                or self.bind_host not in ("0.0.0.0", "127.0.0.1")):
            raise invalid
        try:
            parts = urlsplit(origin)
            if (parts.scheme != "https" or parts.path or parts.query or parts.fragment
                    or parts.username is not None or parts.password is not None
                    or origin != f"https://{parts.netloc}"):
                raise invalid
            authority = _AUTHORITY.fullmatch(parts.netloc)
            if authority is None:
                raise invalid
            hostname, port = authority.groups()
            labels = hostname.split(".")
            if (len(hostname) > 253 or len(labels) < 2
                    or any(_LABEL.fullmatch(label) is None for label in labels)
                    or hostname.endswith((".localhost", ".local", ".internal"))
                    or labels[-1].isdigit()
                    or (port is not None and (int(port) > 65535 or int(port) == 443))):
                raise invalid
            try:
                ipaddress.ip_address(hostname)
            except ValueError:
                pass
            else:
                raise invalid
        except (TypeError, ValueError):
            raise invalid from None

    @property
    def authority(self) -> str:
        return self.public_origin.removeprefix("https://")
