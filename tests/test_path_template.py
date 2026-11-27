"""
:class:`~ape_pie.PathTemplate` formats a url path like an f-string, but escapes every
value so it stays in its own segment, the part of the path between two slashes. It
also parses a path back into the values.

The properties below check that on generated templates and values, with examples to
read. The examples first are for what they don't check: errors, paths that format
doesn't make, and every parse of a path that has more than one.
"""

import string
from collections.abc import Iterable, Iterator
from keyword import iskeyword
from typing import NamedTuple, TypeAlias
from urllib.parse import unquote

import pytest
from furl import furl  # type: ignore
from hypothesis import example, given, reject, settings, strategies as st
from requests import Request
from requests.utils import requote_uri

from ape_pie import APIClient, PathTemplate
from ape_pie.decorators import _parse_template, path_escape

DOT_SEGMENTS = {"", ".", ".."}


# Examples


def test_format_raises_key_error_on_a_missing_value():
    with pytest.raises(KeyError):
        PathTemplate("users/{uid}").format()


def test_match_takes_a_value_unescaped_as_furl_and_django_leave_it():
    assert PathTemplate("users/{uid}").match("users/a,b") == {"uid": "a,b"}


@pytest.mark.parametrize(
    "template,path",
    [
        ("users/{uid}", "users/.."),
        ("users/{uid}", "users/."),
        ("users/{uid}", "users/"),
        ("users/{uid}", "users/%2E%2E"),
        ("users/{uid}", "users"),
        ("users/{uid}", "users/1/orders"),
        ("users/{uid}", "users/1?page=2"),
        ("users/{uid}", "users/a%2"),  # half an escape
        ("users/{uid}", "users/%FF"),  # not UTF-8
        ("users/{uid}", "users/a b"),  # a space must be escaped
        ("{a}/{a}", "x/y"),  # a repeated field with two values
        ("{a}%BC", "%C3%BC"),  # "%C3%BC" is "ü", so "%C3" is half a character
    ],
)
def test_match_returns_none_if_the_path_is_not_formatted_from_the_template(
    template: str, path: str
):
    assert PathTemplate(template).match(path) is None


def test_parse_finds_every_way_to_split_between_fields():
    assert list(PathTemplate("{a}-{b}").parse("x-y-z")) == [
        {"a": "x", "b": "y-z"},
        {"a": "x-y", "b": "z"},
    ]


def test_match_raises_value_error_if_the_path_matches_in_more_than_one_way():
    with pytest.raises(ValueError):
        PathTemplate("{a}-{b}").match("x-y-z")


# Properties


class Field(NamedTuple):
    """A replacement field in a template tree: ``Field("uid")`` prints as ``{uid}``."""

    name: str
    conversion: str | None = None
    format_spec: str = ""

    def __str__(self) -> str:
        conversion = "" if self.conversion is None else f"!{self.conversion}"
        format_spec = f":{self.format_spec}" if self.format_spec else ""
        return f"{{{self.name}{conversion}{format_spec}}}"


Segment: TypeAlias = list[str | Field]


def template_of(tree: list[Segment]) -> str:
    """
    Print a template tree, escaping the braces in its text: ``[["users"], ["v",
    Field("major")]]`` is ``users/v{major}``.
    """
    return "/".join("".join(map(print_part, segment)) for segment in tree)


def print_part(part: str | Field) -> str:
    if isinstance(part, str):
        return part.replace("{", "{{").replace("}", "}}")
    return str(part)


identifiers = st.from_regex(r"[^\W\d]\w*", fullmatch=True).filter(
    lambda s: s.isidentifier() and not iskeyword(s)
)
# template text: a "/" would end the segment, and unquote would decode a "%"
literals = st.text(st.characters(exclude_characters="/%"))
fields = identifiers.map(Field)
trees = st.lists(st.lists(literals | fields), min_size=1)
any_templates = trees.map(template_of)
any_values = st.text() | st.from_type(object)


def fields_of(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


def given_template_and_values(
    templates: st.SearchStrategy[str] = any_templates,
    values: st.SearchStrategy[object] = any_values,
):
    """
    ``@given`` a ``template`` and ``values``: one of ``values`` for each of its fields.
    ``st.shared`` makes the values be for the template the test gets.
    """
    shared_templates = st.shared(templates, key="template")
    return given(
        template=shared_templates,
        values=shared_templates.flatmap(
            lambda template: st.fixed_dictionaries(
                {name: values for name in fields_of(template)}
            )
        ),
    )


def normalise(
    tree: Iterable[Iterable[str | tuple[str, str | None, str]]],
) -> list[Segment]:
    "The tree with adjacent text merged and empty text dropped, which print the same."
    return [list(merge_text(segment)) for segment in tree]


def merge_text(
    segment: Iterable[str | tuple[str, str | None, str]],
) -> Iterator[str | Field]:
    text = ""
    for part in segment:
        if isinstance(part, str):
            text += part
            continue
        if text:
            yield text
        text = ""
        yield Field(*part)
    if text:
        yield text


# a format spec can be anything but braces, even a "/"
any_fields = st.builds(
    Field,
    identifiers,
    st.sampled_from([None, "r", "s", "a"]),
    st.text(st.characters(exclude_characters="{}")),
)


@given(
    st.lists(
        st.lists(st.text(st.characters(exclude_characters="/")) | any_fields),
        min_size=1,
    )
)
@example([["users"], [Field("uid")]])
@example([["v", Field("major"), ".", Field("minor")]])
@example([["{a}"]])
@example([["items"], [Field("v", "r", "/^9")]])
def test_parse_template_inverts_template_of(tree: list[Segment]):
    """
    Parsing a printed template tree gives the tree back, up to how its text is split:
    ``v{major}.{minor}`` parses to ``[["v", Field("major"), ".", Field("minor")]]``.
    """
    assert normalise(_parse_template(template_of(tree))) == normalise(tree)


@given(st.text())
def test_path_escape_round_trips(s: str):
    """
    Unescaping an escaped string gives it back: ``path_escape("a/b")`` is ``"a%2Fb"``,
    which unescapes to ``"a/b"``.
    """
    assert unquote(path_escape(s)) == s


@given(st.text())
@example("a/b?c#d")
def test_path_escape_stays_in_its_segment(s: str):
    """
    An escaped string has no ``/``, ``?`` or ``#``, and requests sends it as it is:
    ``path_escape("a/b?c#d")`` is ``"a%2Fb%3Fc%23d"``.
    """
    escaped = path_escape(s)
    assert not {"/", "?", "#"} & set(escaped)
    assert requote_uri(escaped) == escaped


@given_template_and_values()
@example(template="users/{uid}", values={"uid": "../admin"})
@example(template="users/{uid}", values={"uid": ".."})  # "users/.." is the API root
@example(template="users/{uid}", values={"uid": "."})  # "users/." is "users/"
@example(template="users/{uid}/orders", values={"uid": ""})
@example(template="users/.{uid}", values={"uid": "."})  # the whole segment is ".."
@example(template="users/{uid}.json", values={"uid": "."})  # but this one isn't
@example(template="v{major}.{minor}", values={"major": 1, "minor": 2})
@example(template="health", values={})
def test_format_is_an_f_string_per_segment(template: str, values: dict[str, object]):
    """
    Each segment of the path unescapes to what ``str.format`` makes of that segment of
    the template, so a value never adds or removes a segment: ``users/{uid}`` with
    ``uid="../admin"`` is ``users/..%2Fadmin``, whose segments unescape to ``users``
    and ``../admin``. A segment with a field that would format to ``""``, ``"."`` or
    ``".."`` raises :class:`ValueError` instead.
    """
    segments = template.split("/")  # a field name can't contain a "/"
    expected = [segment.format(**values) for segment in segments]

    if any(
        formatted in DOT_SEGMENTS
        for formatted, segment in zip(expected, segments, strict=True)
        if fields_of(segment)
    ):
        with pytest.raises(ValueError):
            PathTemplate(template).format(**values)
    else:
        path = PathTemplate(template).format(**values)
        assert [unquote(segment) for segment in path.split("/")] == expected


@pytest.mark.parametrize(
    "field", ["{v}", "{v!r}", "{v!s}", "{v!a}", "{v:/^9}", "{v:05d}", "{v:.3}"]
)
@given(v=st.from_type(object))
def test_conversion_and_format_spec_apply_before_escaping(field: str, v: object):
    """
    A conversion or format spec applies to the value before it's escaped, as in an
    f-string, and raises what ``str.format`` raises: ``x/-{v:/^5}`` with ``v=1`` is
    ``x/-%2F%2F1%2F%2F``, which unescapes to ``x/-//1//``.
    """
    template = f"x/-{field}"  # "-" keeps the segment from being a dot-segment
    try:
        expected = template.format(v=v)
    except (TypeError, ValueError) as e:
        with pytest.raises(type(e)):
            PathTemplate(template).format(v=v)
    else:
        assert unquote(PathTemplate(template).format(v=v)) == expected


single_field_segments = st.tuples(literals, fields | st.just(""), literals).map(list)


@given_template_and_values(
    st.lists(single_field_segments, min_size=1).map(template_of), st.text()
)
@example(
    template="zaken/{zaak_uuid}/rollen/{uuid}", values={"zaak_uuid": "1", "uuid": "2"}
)
@example(template="{a}/{a}", values={"a": "x"})
@example(template="users/{uid}", values={"uid": "../admin"})
@example(template="users/{uid}", values={"uid": "a,b"})
def test_parse_inverts_format_with_one_field_per_segment(
    template: str, values: dict[str, object]
):
    """
    With at most one field per segment, the values are the only parse of the path they
    format to: ``zaken/{zaak_uuid}`` with ``zaak_uuid="a/b"`` is ``zaken/a%2Fb``,
    whose only parse is ``{"zaak_uuid": "a/b"}``.
    """
    path_template = PathTemplate(template)
    try:
        path = path_template.format(**values)
    except ValueError:
        reject()  # a segment formats to "", "." or "..", which PathTemplate refuses

    assert list(path_template.parse(path)) == [values]


# One segment, where adjacent fields can split a value anywhere: k adjacent fields
# over n characters have C(n+k-1, k-1) parses. Three parts and short values already
# have every case: adjacent fields, a literal also in a value and a repeated field.
@given_template_and_values(
    st.lists(literals | fields, max_size=3).map(lambda segment: template_of([segment])),
    st.text(max_size=10),
)
@example(template="{a}-{b}", values={"a": "x", "b": "y-z"})
@example(template="{a},{b}", values={"a": "x,y", "b": "z"})
# fields with a separator in real APIs: GitHub's compare/{basehead}, jsDelivr's
# npm/{package}@{version} and an OData composite key
@example(template="{base}...{head}", values={"base": "main", "head": "feature"})
@example(
    template="{package}@{version}", values={"package": "react", "version": "18.3.1"}
)
@example(
    template="Orders(OrderID={order_id},ProductID={product_id})",
    values={"order_id": "10248", "product_id": "11"},
)
def test_parse_finds_the_values_among_every_parse(
    template: str, values: dict[str, object]
):
    """
    The values are among the parses of the path they format to, and every parse
    formats back to that path: ``{a}-{b}`` with ``a="x"`` and ``b="y-z"`` is
    ``x-y-z``, which also parses as ``{"a": "x-y", "b": "z"}``.
    """
    path_template = PathTemplate(template)
    try:
        path = path_template.format(**values)
    except ValueError:
        reject()  # a segment formats to "", "." or "..", which PathTemplate refuses

    parses = list(path_template.parse(path))

    assert values in parses
    assert all(path_template.format(**parse) == path for parse in parses)


# without the examples, "." and ".." are found in 5/20 runs at 100 examples and
# in 20/20 at 1000
@settings(max_examples=1000)
@given(st.text())
@example("../admin")
@example("..")
@example("%2e%2e")
def test_client_requests_the_value_as_one_segment(uid: str):
    """
    requests sends a formatted value as exactly one segment of the URL:
    ``uid="../admin"`` is requested as ``/api/v1/users/..%2Fadmin/orders``, with
    ``../admin`` as one segment.
    """
    client = APIClient("https://example.com/api/v1/")
    try:
        path = PathTemplate("users/{uid}/orders").format(uid=uid)
    except ValueError:
        assert uid in DOT_SEGMENTS
        return

    request = client.prepare_request(Request("GET", client.to_absolute_url(path)))

    assert request.url is not None
    assert furl(request.url).path.segments == ["api", "v1", "users", uid, "orders"]
