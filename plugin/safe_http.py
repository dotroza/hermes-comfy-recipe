"""Outbound HTTP(S) for model downloads and size lookups: public hosts only. Stdlib only, no Hermes imports.

Every request is checked three times:
  1. the URL before the first request: https only, host resolved, every address must be public;
  2. every redirect hop (custom redirect handler), with the same rules;
  3. the connected peer address after TCP connect, so a DNS answer that changes between the check and the
     connection (rebinding) cannot reach an internal host either. Skipped when a user-configured proxy is used:
     the socket peer is then the proxy, and the target was already checked by name.
Private, loopback, link-local (incl. 169.254.169.254), CGNAT, multicast, reserved and unspecified addresses are
refused. ``allow_local=True`` (the plugin setting ``allow_local_mirrors``) additionally admits loopback hosts,
over http or https - for a model mirror on this machine. Other private addresses stay refused.
"""
from __future__ import annotations

import functools
import http.client
import ipaddress
import socket
from urllib import request
from urllib.parse import urlsplit


class BlockedURL(ValueError):
    """The URL or one of its redirect hops points at a non-public host."""


def _ip(text: str):
    a = ipaddress.ip_address(str(text).split('%', 1)[0])
    if isinstance(a, ipaddress.IPv6Address) and a.ipv4_mapped:
        a = a.ipv4_mapped
    return a


def address_allowed(addr: str, allow_local: bool = False) -> bool:
    try:
        a = _ip(addr)
    except ValueError:
        return False
    if a.is_loopback:
        return allow_local
    return a.is_global and not a.is_multicast


def _resolve(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise BlockedURL(f'cannot resolve download host {host!r}: {e}') from None
    return sorted({info[4][0] for info in infos})


def check_url(url: str, allow_local: bool = False, resolve: bool = True) -> str:
    """Return the URL when it is an allowed download link, else raise BlockedURL (a ValueError).
    resolve=False checks scheme and literal addresses only (used when a link is queued, offline)."""
    u = urlsplit(str(url or ''))
    host = (u.hostname or '').rstrip('.').lower()
    if u.scheme not in ('https', 'http') or not host:
        raise BlockedURL(f'Only https download links are accepted: {url!r}')
    try:
        port = u.port or (443 if u.scheme == 'https' else 80)
    except ValueError:
        raise BlockedURL(f'Invalid port in download link: {url!r}') from None
    try:
        literal = _ip(host)
    except ValueError:
        literal = None
    local_name = host == 'localhost' or host.endswith('.localhost')
    loopback = local_name or bool(literal and literal.is_loopback)
    if u.scheme == 'http' and not (allow_local and loopback):
        raise BlockedURL(f'Only https download links are accepted: {url!r}')
    if loopback and not allow_local:
        raise BlockedURL(f'Download links to this machine need the allow_local_mirrors plugin setting: {url!r}')
    if literal is not None:
        if not address_allowed(str(literal), allow_local):
            raise BlockedURL(f'Download links to private or internal addresses are refused: {url!r}')
        return url
    if resolve:
        for addr in _resolve(host, port):
            if not address_allowed(addr, allow_local and local_name):
                raise BlockedURL(f'Download host {host!r} resolves to a private or internal address ({addr}); refused')
    return url


class _GuardedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, allow_local: bool = False, **kw):
        super().__init__(*args, **kw)
        self._allow_local = allow_local

    def connect(self):
        super().connect()
        if self._tunnel_host:  # via a user-configured proxy: the peer is the proxy
            return
        peer = self.sock.getpeername()[0]
        if not address_allowed(peer, self._allow_local):
            self.sock.close()
            raise BlockedURL(f'connection to {self.host!r} reached a private or internal address ({peer}); refused')


class _GuardedHTTPConnection(http.client.HTTPConnection):
    """Plain http is only ever allowed to loopback mirrors (allow_local)."""

    def __init__(self, *args, allow_local: bool = False, **kw):
        super().__init__(*args, **kw)
        self._allow_local = allow_local

    def connect(self):
        super().connect()
        if self._tunnel_host:
            return
        peer = self.sock.getpeername()[0]
        if not (self._allow_local and _ip(peer).is_loopback):
            self.sock.close()
            raise BlockedURL(f'plain http to {self.host!r} ({peer}) is refused')


class _GuardedHTTPSHandler(request.HTTPSHandler):
    def __init__(self, allow_local: bool):
        super().__init__()
        self._allow_local = allow_local

    def do_open(self, http_class, req, **kw):  # swap the connection class, keep urllib's own arguments
        return super().do_open(functools.partial(_GuardedHTTPSConnection, allow_local=self._allow_local), req, **kw)


class _GuardedHTTPHandler(request.HTTPHandler):
    def __init__(self, allow_local: bool):
        super().__init__()
        self._allow_local = allow_local

    def do_open(self, http_class, req, **kw):
        return super().do_open(functools.partial(_GuardedHTTPConnection, allow_local=self._allow_local), req, **kw)


class _GuardedRedirect(request.HTTPRedirectHandler):
    def __init__(self, allow_local: bool):
        self._allow_local = allow_local

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            check_url(newurl, self._allow_local)
        except BlockedURL:
            fp.close()
            raise
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def opener(allow_local: bool = False) -> request.OpenerDirector:
    return request.build_opener(_GuardedHTTPSHandler(allow_local), _GuardedHTTPHandler(allow_local),
                                _GuardedRedirect(allow_local))


def urlopen(req, timeout: float, allow_local: bool = False):
    """urllib.request.urlopen with the public-host checks above. req: a URL string or urllib Request."""
    if isinstance(req, str):
        req = request.Request(req)
    check_url(req.full_url, allow_local)
    return opener(allow_local).open(req, timeout=timeout)
