from keyword import iskeyword
from typing import NamedTuple, TypeAlias
from urllib.parse import unquote

import pytest
from furl import furl  # type: ignore
from hypothesis import example, given, reject, settings, strategies as st
from requests import Request
from requests.utils import requote_uri

from ape_pie import APIClient
from ape_pie.decorators import PathTemplate, path_escape

DOT_SEGMENTS = {"", ".", ".."}


@given(st.text())
def test_path_escape_round_trips(s: str):
    assert unquote(path_escape(s)) == s


@given(st.text())
def test_path_escape_stays_in_its_segment(s: str):
    escaped = path_escape(s)
    assert not {"/", "?", "#"} & set(escaped)
    assert requote_uri(escaped) == escaped  # requests sends it as is


class Field(NamedTuple):
    name: str


Segment: TypeAlias = list[str | Field]

identifiers = st.from_regex(r"[^\W\d]\w*", fullmatch=True).filter(
    lambda s: s.isidentifier() and not iskeyword(s)
)
# a "/" in the literal text separates segments; unquote would decode a "%"
literals = st.text(st.characters(exclude_characters="/%"))
segments = st.lists(st.lists(literals | identifiers.map(Field)), min_size=1)
any_values = st.text() | st.from_type(object)


def template_of(segment: Segment) -> str:
    return "".join(
        part.replace("{", "{{").replace("}", "}}")
        if isinstance(part, str)
        else f"{{{part.name}}}"
        for part in segment
    )


@st.composite
def templates_with_values(
    draw: st.DrawFn,
    templates: st.SearchStrategy[list[Segment]] = segments,
    values: st.SearchStrategy[object] = any_values,
) -> tuple[list[Segment], dict[str, object]]:
    template = draw(templates)
    names = {part.name for seg in template for part in seg if isinstance(part, Field)}
    return template, draw(st.fixed_dictionaries({name: values for name in names}))


@given(templates_with_values())
@example(([["users"], [Field("uid")]], {"uid": "../admin"}))
@example(([["users"], [Field("uid")]], {"uid": ".."}))
@example(([["users"], [Field("uid")], ["orders"]], {"uid": ""}))
@example(([["users"], [".", Field("uid")]], {"uid": "."}))
@example(([["health"]], {}))
def test_format_is_an_f_string_per_segment(
    template_values: tuple[list[Segment], dict[str, object]],
):
    template, values = template_values
    path_template = PathTemplate("/".join(map(template_of, template)))
    expected = [template_of(segment).format(**values) for segment in template]

    if any(
        formatted in DOT_SEGMENTS
        for formatted, segment in zip(expected, template, strict=True)
        if any(isinstance(part, Field) for part in segment)
    ):
        with pytest.raises(ValueError):
            path_template.format(**values)
    else:
        path = path_template.format(**values)
        assert [unquote(segment) for segment in path.split("/")] == expected


@pytest.mark.parametrize(
    "field", ["{v}", "{v!r}", "{v!s}", "{v!a}", "{v:/^9}", "{v:05d}", "{v:.3}"]
)
@given(v=st.from_type(object))
def test_conversion_and_format_spec_apply_before_escaping(field: str, v: object):
    template = f"x/-{field}"  # "-" keeps the segment from being a dot-segment
    try:
        expected = template.format(v=v)
    except (TypeError, ValueError) as e:
        with pytest.raises(type(e)):
            PathTemplate(template).format(v=v)
    else:
        assert unquote(PathTemplate(template).format(v=v)) == expected


single_field_segments = st.tuples(
    literals, st.lists(identifiers.map(Field), max_size=1), literals
).map(lambda parts: [parts[0], *parts[1], parts[2]])


@given(templates_with_values(st.lists(single_field_segments, min_size=1), st.text()))
@example(
    (
        [["zaken"], [Field("zaak_uuid")], ["rollen"], [Field("uuid")]],
        {"zaak_uuid": "1", "uuid": "2"},
    )
)
@example(([[Field("a")], [Field("a")]], {"a": "x"}))
def test_parse_inverts_format_with_one_field_per_segment(
    template_values: tuple[list[Segment], dict[str, object]],
):
    template, values = template_values
    path_template = PathTemplate("/".join(map(template_of, template)))
    try:
        path = path_template.format(**values)
    except ValueError:
        reject()  # a dot-segment

    assert list(path_template.parse(path)) == [values]


# one segment: the parses of segments multiply, and adjacent fields have many
@given(
    templates_with_values(
        st.lists(literals | identifiers.map(Field), max_size=4).map(lambda s: [s]),
        st.text(),
    )
)
@example(([[Field("a"), "-", Field("b")]], {"a": "x", "b": "y-z"}))
@example(([[Field("a"), ",", Field("b")]], {"a": "x,y", "b": "z"}))
def test_parse_finds_the_values_among_every_parse(
    template_values: tuple[list[Segment], dict[str, object]],
):
    template, values = template_values
    path_template = PathTemplate("/".join(map(template_of, template)))
    try:
        path = path_template.format(**values)
    except ValueError:
        reject()  # a dot-segment

    parses = list(path_template.parse(path))

    assert values in parses
    assert all(path_template.format(**parse) == path for parse in parses)


def test_parse_finds_every_way_to_split_between_fields():
    template = PathTemplate("{a}-{b}")

    assert list(template.parse("x-y-z")) == [
        {"a": "x", "b": "y-z"},
        {"a": "x-y", "b": "z"},
    ]
    with pytest.raises(ValueError):
        template.match("x-y-z")


@pytest.mark.parametrize(
    "path",
    [
        "users/..",
        "users/.",
        "users/",
        "users/%2E%2E",
        "users",
        "users/1/orders",
        "users/1?page=2",
        "users/a%2",
        "users/%FF",
        "users/a b",
    ],
)
def test_match_returns_none_if_path_is_not_formatted_from_template(path: str):
    assert PathTemplate("users/{uid}").match(path) is None


# without the examples, "." and ".." are found in 5/20 runs at 100 examples and
# in 20/20 at 1000
@settings(max_examples=1000)
@given(st.text())
@example("../admin")
@example("..")
@example("%2e%2e")
def test_client_requests_the_value_as_one_segment(uid: str):
    client = APIClient("https://example.com/api/v1/")
    try:
        path = PathTemplate("users/{uid}/orders").format(uid=uid)
    except ValueError:
        assert uid in DOT_SEGMENTS
        return

    request = client.prepare_request(Request("GET", client.to_absolute_url(path)))

    assert request.url is not None
    assert furl(request.url).path.segments == ["api", "v1", "users", uid, "orders"]


def test_match_requires_a_repeated_field_to_have_one_value():
    template = PathTemplate("{a}/{a}")

    assert template.match("x/x") == {"a": "x"}
    assert template.match("x/y") is None


def test_match_does_not_split_a_character():
    # "%C3%BC" is "ü": "%C3" is half a character, not a value
    assert PathTemplate("{a}%BC").match("%C3%BC") is None
