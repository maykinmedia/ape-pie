# mypy: warn-unused-ignores
# pyright: reportUnnecessaryTypeIgnoreComment=true
"""
Static checks of the types :class:`ape_pie.endpoint` gives, for mypy (``tox -e mypy``)
and pyright. Pytest doesn't collect this file and nothing in it runs.

``assert_type`` checks an inferred type. A ``# type: ignore[code]`` marks an expected
error; unused ignores are errors, so the check fails if the expected error goes away.
"""

from collections.abc import Callable
from typing import ParamSpec, TypeVar, assert_type

from ape_pie import EndpointMethod, URLPath, endpoint

_P = ParamSpec("_P")
_T = TypeVar("_T")


def interchangeable(f: Callable[_P, _T], /) -> Callable[[Callable[_P, _T]], None]:
    """
    ``interchangeable(f)(g)`` type checks if ``g`` can stand in for ``f``.

    Checked both ways round, ``f`` and ``g`` have the same signature, including the
    parameter names, kinds and defaults ``assert_type`` can't take from a ``Callable``.
    """
    return lambda g: None


@endpoint("foos")
def list_foos(url_path: str) -> list[bytes]:
    return [url_path.encode()]


@endpoint("foos/{foo_id}")
def get_foo(url_path: str, foo_id: int, verbose: bool = False) -> bytes:
    return url_path.encode()


@endpoint("foos/{foo_id}")
def get_foo_positionally(url_path: str, foo_id: int, verbose: bool, /) -> bytes:
    return url_path.encode()


class Client:
    @endpoint("foos/{foo_id}")
    def get_foo(self, url_path: str, foo_id: int, verbose: bool = False) -> bytes:
        return url_path.encode()

    @endpoint("foos/{foo_id}")
    def get_foo_positionally(
        self, url_path: str, foo_id: int, verbose: bool, /
    ) -> bytes:
        return url_path.encode()


# an endpoint can override an endpoint, like a method a method
class V2Client(Client):
    @endpoint("v2/foos/{foo_id}")
    def get_foo(self, url_path: str, foo_id: int, verbose: bool = False) -> bytes:
        return url_path.encode()


def get_foo_signature(foo_id: int, verbose: bool = False) -> bytes:
    "``get_foo`` without the url path"
    raise NotImplementedError


def unbound_get_foo_signature(
    self: Client, /, foo_id: int, verbose: bool = False
) -> bytes:
    "``Client.get_foo`` without the url path, its self positional-only by Concatenate"
    raise NotImplementedError


def check_positional_function_is_a_callable_without_the_url_path() -> None:
    assert_type(list_foos, Callable[[], list[bytes]])
    assert_type(get_foo_positionally, Callable[[int, bool], bytes])


def check_positional_method_is_a_callable_without_the_url_path() -> None:
    assert_type(Client().get_foo_positionally, Callable[[int, bool], bytes])
    assert_type(Client.get_foo_positionally, Callable[[Client, int, bool], bytes])


def check_function_has_its_signature_without_the_url_path() -> None:
    interchangeable(get_foo)(get_foo_signature)
    interchangeable(get_foo_signature)(get_foo)


def check_method_on_an_instance_has_its_signature_without_the_url_path() -> None:
    interchangeable(Client().get_foo)(get_foo_signature)
    interchangeable(get_foo_signature)(Client().get_foo)


def check_method_on_the_class_has_its_signature_without_the_url_path() -> None:
    interchangeable(Client.get_foo)(unbound_get_foo_signature)
    interchangeable(unbound_get_foo_signature)(Client.get_foo)


def check_interchangeable_tells_names_kinds_and_defaults_apart() -> None:
    def renamed(foo: int, verbose: bool = False) -> bytes:
        raise NotImplementedError

    def keyword_only(*, foo_id: int, verbose: bool = False) -> bytes:
        raise NotImplementedError

    def no_default(foo_id: int, verbose: bool) -> bytes:
        raise NotImplementedError

    interchangeable(get_foo_signature)(renamed)  # type: ignore[arg-type]
    interchangeable(get_foo_signature)(keyword_only)  # type: ignore[arg-type]
    interchangeable(get_foo_signature)(no_default)  # type: ignore[arg-type]


def check_interchangeable_needs_both_ways_round() -> None:
    def more(foo_id: int, verbose: bool = False, page: int = 1) -> bytes:
        raise NotImplementedError

    interchangeable(get_foo_signature)(more)
    interchangeable(more)(get_foo_signature)  # type: ignore[arg-type]


def check_function_must_take_a_str_url_path() -> None:
    @endpoint("foos")  # type: ignore[arg-type]
    def takes_nothing() -> None: ...

    @endpoint("foos")  # type: ignore[arg-type]
    def takes_an_int(url_path: int) -> None: ...


def get_foo_method(self: Client, url_path: URLPath, foo_id: int) -> bytes:
    return url_path.encode()


# inferred without the annotation as context, so these check the type endpoint infers
def check_endpoint_method_annotates_a_decorated_method() -> EndpointMethod[
    Client, [int], bytes
]:
    method = endpoint("foos/{foo_id}")(get_foo_method)
    return method


def check_endpoint_method_annotation_has_the_parameter_types() -> EndpointMethod[
    Client, [str], bytes
]:
    method = endpoint("foos/{foo_id}")(get_foo_method)
    return method  # type: ignore[return-value]


@endpoint("foos")
def takes_the_url_path_second(client: Client, url_path: str) -> None: ...


def check_function_taking_the_url_path_second_is_only_a_method() -> None:
    # at runtime, client would get the url path and url_path the client
    takes_the_url_path_second(Client())  # type: ignore[operator]
