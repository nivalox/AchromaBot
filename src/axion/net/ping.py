"""Ping measurements: your own connection, the bikesense.org website and the chat API."""
import socket
import statistics
import time

import requests

from axion.constants import CLIENT_PING_HOSTS, SITE_URL

from .http import HEADERS

SAMPLES = 3
TIMEOUT = 4


def tcp_ms(host, port):
    """Milliseconds to open a TCP connection. Works without root, unlike an ICMP ping."""
    start = time.perf_counter()
    with socket.create_connection((host, port), timeout=TIMEOUT):
        pass
    return (time.perf_counter() - start) * 1000


def https_ms(url):
    """Milliseconds until the site starts answering, on a fresh connection (DNS, TCP and TLS included)."""
    start = time.perf_counter()
    r = requests.get(
        url, headers={"user-agent": HEADERS["user-agent"]}, timeout=TIMEOUT, stream=True, allow_redirects=False,
    )
    ms = (time.perf_counter() - start) * 1000
    r.close()
    return ms


def median_ms(fn, *args):
    """The median of a few samples, or None if the first one already fails."""
    times = []
    for _ in range(SAMPLES):
        try:
            times.append(fn(*args))
        except (OSError, requests.RequestException):
            break
    return statistics.median(times) if times else None


def client_ping():
    """Latency of this device's own internet connection, measured against public DNS servers."""
    for host, port in CLIENT_PING_HOSTS:
        ms = median_ms(tcp_ms, host, port)
        if ms is not None:
            return ms
    return None


def site_ping():
    return median_ms(https_ms, SITE_URL)


def measure_all(api_ms):
    """Everything ?ping shows. api_ms is the round trip of the last chat poll, which costs nothing extra."""
    return {"client": client_ping(), "site": site_ping(), "api": api_ms}
