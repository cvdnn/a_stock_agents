"""Offline-only Uvicorn entrypoint for authenticated browser E2E."""
from __future__ import annotations

import argparse
import ipaddress
import socket


_original_connect = socket.socket.connect
_original_getaddrinfo = socket.getaddrinfo


def _is_loopback_host(host: object) -> bool:
    value = str(host or "").strip().lower()
    if value == "localhost":
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def _loopback_only_getaddrinfo(host, port, *args, **kwargs):
    if not _is_loopback_host(host):
        raise socket.gaierror("browser E2E blocks non-loopback DNS resolution")
    return _original_getaddrinfo(host, port, *args, **kwargs)


def _loopback_only_connect(sock: socket.socket, address):
    host = address[0] if isinstance(address, tuple) and address else ""
    if _is_loopback_host(host):
        return _original_connect(sock, address)
    raise OSError("browser E2E blocks non-loopback outbound connections")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    socket.getaddrinfo = _loopback_only_getaddrinfo
    socket.socket.connect = _loopback_only_connect

    import uvicorn

    uvicorn.run("server.app:app", host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
