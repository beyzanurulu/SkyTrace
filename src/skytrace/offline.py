"""Offline mode (``SKYTRACE_MODE=offline``): nothing may leave the machine.

Three layers:

1. **Config check**: the chat model and the embedding model must be local
   (Ollama) and their servers must be on an allowed host (``offline.allowed_hosts``).
2. **Network guard**: ``socket.getaddrinfo`` and ``socket.socket.connect`` refuse
   every host that is not allowed (loopback always is), so a library that tries
   to phone home fails loudly instead of leaking data. Refused attempts are
   recorded in :data:`BLOCKED`.
3. **No downloads**: LiteLLM uses its bundled model cost map instead of fetching
   it from GitHub, and ``skytrace docs build`` (which clones repositories) refuses.

Incoming connections (the web UI) are not affected: the guard only covers
outgoing connects and name lookups.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Final
from urllib.parse import urlparse

from skytrace.config import LOCAL_MODEL_PREFIXES, ConfigError, SkyTraceConfig

MODE_ENV: Final = "SKYTRACE_MODE"
MODES: Final = ("online", "offline")
# Environment that keeps libraries from downloading anything at import / first use.
OFFLINE_ENV: Final = {"LITELLM_LOCAL_MODEL_COST_MAP": "True"}

BLOCKED: list[str] = []  # "host:port" of every refused attempt, for reports and tests


class OfflineError(ConfigError):
    """The configuration would send data off the machine in offline mode."""


class OfflineNetworkError(OSError):
    """A connection to a host outside ``offline.allowed_hosts`` was refused."""


def mode() -> str:
    value = os.environ.get(MODE_ENV, "online").strip().lower() or "online"
    if value not in MODES:
        raise ConfigError(f"{MODE_ENV} must be one of {', '.join(MODES)}, got {value!r}")
    return value


def is_offline() -> bool:
    return mode() == "offline"


def _host(url: str | None) -> str | None:
    return urlparse(url).hostname if url else None


def check_config(cfg: SkyTraceConfig) -> None:
    """Raise OfflineError listing every setting that is not local."""
    allowed = {h.lower() for h in cfg.offline.allowed_hosts}
    problems = []
    for key, model in (
        ("agent.model", cfg.agent.model),
        ("rag.embedding_model", cfg.rag.embedding_model),
    ):
        if not model.startswith(LOCAL_MODEL_PREFIXES):
            problems.append(f"{key} = {model!r} is not a local (Ollama) model")
    for key, url in (("agent.api_base", cfg.agent.api_base), ("rag.api_base", cfg.rag.api_base)):
        host = _host(url)
        if host is None:
            problems.append(f"{key} must point to the local model server (it is empty)")
        elif host.lower() not in allowed:
            problems.append(f"{key} = {url!r}: host {host!r} is not in offline.allowed_hosts")
    if problems:
        raise OfflineError("offline mode (SKYTRACE_MODE=offline): " + "; ".join(problems))


# --- network guard ----------------------------------------------------------------

_real_getaddrinfo = socket.getaddrinfo
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex
_allowed_names: set[str] = set()
_allowed_ips: set[str] = set()


def _is_loopback(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def _ip_allowed(ip: str) -> bool:
    return _is_loopback(ip) or ip in _allowed_ips


def _refuse(host: object, port: object) -> OfflineNetworkError:
    target = f"{host}:{port}"
    BLOCKED.append(target)
    return OfflineNetworkError(
        f"offline mode: connection to {target} refused (offline.allowed_hosts)"
    )


def _guarded_getaddrinfo(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
    name = host.decode() if isinstance(host, bytes) else host
    if name is None or str(name).lower() in _allowed_names or _ip_allowed(str(name)):
        return _real_getaddrinfo(host, port, *args, **kwargs)
    raise _refuse(name, port)


def _check_address(sock: socket.socket, address: Any) -> None:  # noqa: ANN401
    if sock.family in (socket.AF_INET, socket.AF_INET6) and isinstance(address, tuple):
        host = str(address[0])
        if not (_ip_allowed(host) or host.lower() in _allowed_names):
            raise _refuse(host, address[1])


def _guarded_connect(self: socket.socket, address: Any) -> None:  # noqa: ANN401
    _check_address(self, address)
    _real_connect(self, address)


def _guarded_connect_ex(self: socket.socket, address: Any) -> int:  # noqa: ANN401
    _check_address(self, address)
    return _real_connect_ex(self, address)


def install_network_guard(allowed_hosts: list[str]) -> None:
    """Refuse outgoing connections except to loopback and ``allowed_hosts``."""
    names = {h.lower() for h in allowed_hosts}
    ips: set[str] = set()
    for name in names:
        try:  # e.g. the "ollama" service of docker compose
            ips.update(str(info[4][0]) for info in _real_getaddrinfo(name, None))
        except OSError:
            continue
    _allowed_names.clear()
    _allowed_names.update(names)
    _allowed_ips.clear()
    _allowed_ips.update(ips)
    socket.getaddrinfo = _guarded_getaddrinfo
    socket.socket.connect = _guarded_connect  # type: ignore[method-assign,assignment]
    socket.socket.connect_ex = _guarded_connect_ex  # type: ignore[method-assign,assignment]


def remove_network_guard() -> None:
    socket.getaddrinfo = _real_getaddrinfo
    socket.socket.connect = _real_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = _real_connect_ex  # type: ignore[method-assign]


@contextmanager
def network_guard(allowed_hosts: list[str]) -> Iterator[None]:
    install_network_guard(allowed_hosts)
    try:
        yield
    finally:
        remove_network_guard()


def activate(cfg: SkyTraceConfig) -> None:
    """Enter offline mode for this process: check the config, then guard the network."""
    check_config(cfg)
    for key, value in OFFLINE_ENV.items():
        os.environ.setdefault(key, value)
    install_network_guard(list(cfg.offline.allowed_hosts))
