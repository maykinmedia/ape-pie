from __future__ import annotations

from collections.abc import Callable
from http.cookiejar import CookieJar
from typing import (
    TYPE_CHECKING,
    Concatenate,
    ParamSpec,
    Protocol,
    TypeAlias,
    TypedDict,
    TypeVar,
    overload,
)

from requests.cookies import RequestsCookieJar

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
    """
        Supposed to be ParamSpec.kwargs of `requests.request`
    `"""

    # from BaseRequestKwargs - modern requests versions have requests._types
    headers: _HeadersMapping
    cookies: RequestsCookieJar | CookieJar | _TextMapping | None
    files: _Files | None
    auth: _Auth | None
    timeout: _Timeout | None
    allow_redirects: bool
    proxies: _TextMapping | None
    hooks: _HooksInput | None
    stream: bool | None
    verify: _Verify | None
    cert: _Cert | None
    # from RequestKwargs, which subclasses BaseRequestKwargs
    params: _Params
    data: _Data
    json: Incomplete
    # not taken directly by requests.request, but can be set on requests.Session,
    # see :attr:`requests.Session.__attrs__`
    trust_env: bool
    max_redirects: int


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


_P = ParamSpec("_P")
_T_co = TypeVar("_T_co", covariant=True)
_S_contra = TypeVar("_S_contra", contravariant=True)

URLPath: TypeAlias = str
"The url path :class:`ape_pie.endpoint` passes to the function it decorates."


class EndpointMethod(Protocol[_S_contra, _P, _T_co]):
    """
    A method decorated with :class:`ape_pie.endpoint`: on an instance of
    ``_S_contra`` it takes the parameters ``_P`` and returns ``_T_co``.
    """

    @overload
    def __get__(
        self, instance: None, owner: type[object] | None = None, /
    ) -> Callable[Concatenate[_S_contra, _P], _T_co]: ...
    @overload
    def __get__(
        self, instance: _S_contra, owner: type[object] | None = None, /
    ) -> Callable[_P, _T_co]: ...
