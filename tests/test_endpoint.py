import inspect
from collections.abc import Callable

import pytest
from hypothesis import example, given, strategies as st

from ape_pie.decorators import PathTemplate, endpoint

# ".json" keeps the segment from formatting to a dot-segment, which raises ValueError
TEMPLATE = "foo/{foo_id}.json"


@endpoint(TEMPLATE)
def by_name(
    url_path: str, foo_id: object = "default", other: bool = False
) -> tuple[str, object, bool]:
    return url_path, foo_id, other


@endpoint(TEMPLATE)
def keyword_only(
    url_path: str, *, foo_id: object, other: bool
) -> tuple[str, object, bool]:
    return url_path, foo_id, other


@endpoint(TEMPLATE)
def var_keyword(
    url_path: str, other: bool, **kwargs: object
) -> tuple[str, object, bool]:
    return url_path, kwargs["foo_id"], other


class Client:
    @endpoint(TEMPLATE)
    def get(
        self, url_path: str, foo_id: object, other: bool
    ) -> tuple[str, object, bool]:
        assert isinstance(self, Client)
        return url_path, foo_id, other


CALLS: dict[str, Callable[[object, bool], tuple[str, object, bool]]] = {
    "positional": lambda foo_id, other: by_name(foo_id, other),
    "keyword": lambda foo_id, other: by_name(foo_id=foo_id, other=other),
    "keyword-only": lambda foo_id, other: keyword_only(foo_id=foo_id, other=other),
    "**kwargs": lambda foo_id, other: var_keyword(other, foo_id=foo_id),
    "method": lambda foo_id, other: Client().get(foo_id, other),
    "method on class": lambda foo_id, other: Client.get(Client(), foo_id, other),
}


@pytest.mark.parametrize("other", [True, False])
@pytest.mark.parametrize("call", CALLS.values(), ids=list(CALLS))
@given(foo_id=st.from_type(object))
@example(foo_id="../../injection")
def test_formats_the_url_path_from_the_arguments(
    call: Callable[[object, bool], tuple[str, object, bool]],
    other: bool,
    foo_id: object,
):
    url_path, received_foo_id, received_other = call(foo_id, other)

    assert received_foo_id is foo_id
    assert received_other is other
    assert url_path == PathTemplate(TEMPLATE).format(foo_id=foo_id)


def test_formats_the_url_path_from_defaults():
    assert by_name() == ("foo/default.json", "default", False)


@given(foo_id=st.integers())
def test_ints_need_no_escaping(foo_id: int):
    url_path, *_ = by_name(foo_id)

    assert url_path == f"foo/{foo_id}.json"


def test_signature_leaves_out_the_url_path():
    assert list(inspect.signature(by_name).parameters) == ["foo_id", "other"]
    assert list(inspect.signature(Client().get).parameters) == ["foo_id", "other"]
    assert list(inspect.signature(Client.get).parameters) == [
        "self",
        "foo_id",
        "other",
    ]


@pytest.mark.parametrize(
    "call",
    [
        lambda: keyword_only(other=True),  # type: ignore[call-arg]
        lambda: var_keyword(other=True),
        lambda: Client.get(),  # type: ignore[call-arg]
    ],
)
def test_raises_type_error_on_missing_arguments(call: Callable[[], object]):
    with pytest.raises(TypeError):
        call()


def takes_no_url_path(*, foo_id: object) -> None: ...
def foo_id_is_the_url_path(foo_id: str) -> None: ...
def has_no_foo_id(url_path: str, bar: object) -> None: ...
def foo_id_is_var_positional(url_path: str, *foo_id: object) -> None: ...
def foo_id_is_var_keyword(url_path: str, **foo_id: object) -> None: ...


@pytest.mark.parametrize(
    "f",
    [
        takes_no_url_path,
        foo_id_is_the_url_path,
        has_no_foo_id,
        foo_id_is_var_positional,
        foo_id_is_var_keyword,
    ],
)
def test_raises_type_error_if_function_cannot_take_the_path(
    f: Callable[..., None],
):
    with pytest.raises(TypeError):
        endpoint("foo/{foo_id}")(f)


def test_raises_type_error_on_access_if_method_cannot_take_the_path():
    class Client:
        @endpoint("foo/{url_path}")
        def get(self, url_path: str) -> None: ...

    with pytest.raises(TypeError):
        _ = Client().get


@pytest.mark.parametrize(
    "path",
    [
        # invalid python parameter names
        "/{class}",
        "/{def}",
        "/{1foo}",
        "/{foo\n}",
        # positional fields
        "/{}",
        "/{0}",
        # they're not f-strings
        "/foo/{my_foo.id}",
        "/foo/{my_foo[0]}",
        "/foo/{my_foo!x}",
        "/foo/{my_foo:{width}}",
        # unbalanced braces
        "/foo/{",
        "/foo/}",
    ],
)
def test_raises_value_error_on_invalid_path_parameters(path: str):
    with pytest.raises(ValueError):
        endpoint(path)


@pytest.mark.parametrize("path", ["/{café}", "/{foo!r}", "/{foo:>5}", "/{{foo}}"])
def test_accepts_identifiers_conversions_and_format_specs(path: str):
    endpoint(path)
