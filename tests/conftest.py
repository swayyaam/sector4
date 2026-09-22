"""Shared test setup.

The one rule that matters here: a test must never reach the network. Jolpica
and the F1 timing API are rate-limited shared resources, and a test suite that
quietly spends that budget is worse than one that fails loudly. This is
enforced rather than documented, because a convention only holds until someone
adds a test in a hurry.
"""
from __future__ import annotations

import socket

import pytest

_real_connect = socket.socket.connect
_real_create_connection = socket.create_connection
_LOCAL = {"127.0.0.1", "::1", "localhost", ""}


class NetworkAccessDenied(RuntimeError):
    pass


def _host_of(address) -> str:
    if isinstance(address, tuple) and address:
        return str(address[0])
    return str(address)


def _deny(address) -> None:
    host = _host_of(address)
    if host not in _LOCAL:
        raise NetworkAccessDenied(
            f"a test tried to open a network connection to {host!r}. "
            "Tests run against committed fixtures; nothing here may call Jolpica, "
            "FastF1, or any other API."
        )


@pytest.fixture(autouse=True, scope="session")
def _no_network():
    def connect(self, address):
        _deny(address)
        return _real_connect(self, address)

    def create_connection(address, *args, **kwargs):
        _deny(address)
        return _real_create_connection(address, *args, **kwargs)

    socket.socket.connect = connect
    socket.create_connection = create_connection
    try:
        yield
    finally:
        socket.socket.connect = _real_connect
        socket.create_connection = _real_create_connection
