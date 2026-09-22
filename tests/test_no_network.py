"""The guard that keeps the rest of the suite honest."""
from __future__ import annotations

import socket

import pytest

from conftest import NetworkAccessDenied


def test_outbound_connections_are_blocked():
    with pytest.raises(NetworkAccessDenied, match="Jolpica"):
        socket.create_connection(("api.jolpi.ca", 443), timeout=1)


def test_the_f1_timing_api_is_blocked_too():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(NetworkAccessDenied):
        s.connect(("livetiming.formula1.com", 443))


def test_localhost_is_still_reachable():
    """Blocking everything would break unrelated tooling; only egress is denied."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    try:
        socket.create_connection(srv.getsockname(), timeout=2).close()
    finally:
        srv.close()
