"""The suite runs offline: conftest blocks every non-loopback connection and DNS lookup."""

from __future__ import annotations

import socket

import pytest


def test_a_connection_to_the_outside_is_blocked():
    with pytest.raises(RuntimeError, match="blocked in tests"):
        socket.create_connection(("203.0.113.7", 443), timeout=1)


def test_a_dns_lookup_is_blocked():
    with pytest.raises(RuntimeError, match="DNS lookup is blocked"):
        socket.getaddrinfo("generativelanguage.googleapis.com", 443)


def test_no_google_or_sib_variable_leaks_into_a_test():
    import os

    assert not [k for k in os.environ if k.startswith(("SIB_", "GOOGLE_", "GEMINI_"))]
