from __future__ import annotations

from http.cookiejar import CookieJar
from typing import TYPE_CHECKING, Protocol, TypedDict

if TYPE_CHECKING:
    # imports from stubs
    from _typeshed import Incomplete
    from requests.api import _HeadersMapping
    from requests.sessions import (
        _Auth,
        _Cert,
        _Data,
        _Files,
        _HooksInput,
        _Params,
        _TextMapping,
        _Timeout,
        _Verify,
    )


class RequestKwargs(TypedDict, total=False):
    # Supposed to be ParamSpec.kwargs of `requests.request`
    params: _Params
    data: _Data
    headers: _HeadersMapping
    cookies: CookieJar | _TextMapping | None
    files: _Files | None
    auth: _Auth | None
    timeout: _Timeout | None
    allow_redirects: bool
    proxies: _TextMapping | None
    hooks: _HooksInput | None
    stream: bool | None
    verify: _Verify | None
    cert: _Cert | None
    json: Incomplete


class ConfigAdapter(Protocol):
    def get_client_base_url(self) -> str:  # pragma: no cover
        """
        Return the API root/base URL to which relative URLs are made.
        """
        ...

    def get_client_session_kwargs(self) -> RequestKwargs:  # pragma: no cover
        """
        Return kwargs to feed to :class:`requests.Session` when using the client.

        Provide a dict of possible :class:`requests.Session` attributes which will
        (typically) be used as defaults for each request sent from the session, such as
        ``auth`` for authentication or ``cert`` and/or ``verify`` for mutual TLS
        purposes. Other examples would be a ``timeout`` that's service-specific (and
        potentially different from the global default).

        Note that many of these kwargs can still be overridden at call time, e.g.:

        .. code-block:: python

            with APIClient.configure_from(some_service) as client:
                response = client.get("some/relative/path", timeout=10)
        """
        ...
