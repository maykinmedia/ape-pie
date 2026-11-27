"""
Because it is easy to forget to correctly escape user strings as path parameters.

:class:`PathTemplate` formats a url path like an f-string, but keeps every value inside
the path segment it was put in. :class:`endpoint` decorates a function with a template,
and formats the url path from the function's own arguments.
"""

from __future__ import annotations

import inspect
import re
import string
from codecs import getincrementaldecoder
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from functools import cache, cached_property, update_wrapper
from itertools import islice
from keyword import iskeyword
from types import MethodType
from typing import (
    Concatenate,
    NamedTuple,
    ParamSpec,
    TypeAlias,
    TypeVar,
    overload,
)
from urllib.parse import quote, unquote, unquote_to_bytes

from .typing import EndpointMethod, URLPath

_P = ParamSpec("_P")
_T = TypeVar("_T")
_S = TypeVar("_S")


def path_escape(string: str) -> str:
    """
    Escape a string so it stays within one url path segment.

    ``"."`` and ``".."`` are left as they are; :class:`PathTemplate` rejects them.
    """
    return quote(string, safe="")


class _Field(NamedTuple):
    "A replacement field ``{name!conversion:format_spec}`` of a :class:`PathTemplate`."

    name: str
    conversion: str | None
    format_spec: str

    def render(self, value: object) -> str:
        if self.conversion is not None:
            value = _CONVERSIONS[self.conversion](value)
        return path_escape(format(value, self.format_spec))


_Segment: TypeAlias = tuple[str | _Field, ...]
_CONVERSIONS: Mapping[str, Callable[[object], str]] = {"r": repr, "s": str, "a": ascii}
_DOT_SEGMENTS = frozenset({"", ".", ".."})
# a character of a value in a path segment: unreserved, a sub-delim, ":" or "@", which
# furl and Django leave unescaped, or percent-encoded
_SEGMENT_CHAR = re.compile(r"[A-Za-z0-9_.~!$&'()*+,;=:@-]|%[0-9A-Fa-f]{2}")
_Matcher: TypeAlias = Callable[[dict[str, str]], Iterator[dict[str, str]]]


class PathTemplate:
    """
    A url path with ``{name}`` replacement fields, formatted like an f-string, but with
    every value escaped so it stays within its path segment.

    >>> PathTemplate("users/{uid}/orders").format(uid="../admin")
    'users/..%2Fadmin/orders'

    A conversion (``!r``) or format spec (``:05d``) applies to the value before it is
    escaped, as in an f-string. A segment with a field in it must not format to ``""``,
    ``"."`` or ``".."``, which would address another resource (``users/`` for
    ``users/{uid}``) or be removed by URL normalization; that raises
    :class:`ValueError`.

    :meth:`parse` and :meth:`match` go the other way, from a path to the values, e.g.
    to get the ids out of a resource URL an API returned.

    >>> PathTemplate("zaken/{zaak_uuid}/rollen/{uuid}").match("zaken/1a/rollen/2b")
    {'zaak_uuid': '1a', 'uuid': '2b'}

    Laws, for a template ``t`` without ``%`` in its literal text and ``p =
    PathTemplate(t)``:

    * ``[unquote(s) for s in p.format(**v).split("/")]`` is ``t`` split on the ``/``
      in its literal text, each segment formatted with ``**v``. So the values never
      add or remove a segment, and ``unquote(p.format(**v)) == t.format(**v)``.
    * For string values and fields without a conversion or format spec, ``v`` is in
      ``p.parse(p.format(**v))``, and every ``w`` in ``p.parse(path)`` formats to
      ``path``, up to the percent-encoding in each segment.
    * With at most one field per segment, ``p.parse(path)`` has at most one parse.
    """

    template: str
    fields: frozenset[str]

    def __init__(self, template: str) -> None:
        self.template = template
        self._segments = _parse_template(template)
        self.fields = frozenset(
            part.name
            for segment in self._segments
            for part in segment
            if isinstance(part, _Field)
        )

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.template!r})"

    def format(self, /, **values: object) -> str:
        return self.format_map(values)

    def format_map(self, values: Mapping[str, object]) -> str:
        return "/".join(_format_segment(segment, values) for segment in self._segments)

    def parse(self, path: str) -> Iterator[dict[str, str]]:
        """
        Every way ``path`` can be formatted from this template, as the field values.

        The values are the formatted strings, unescaped: ``"00005"`` for ``{i:05d}``.
        A path can have more than one parse if a segment has two fields, like
        ``{a}-{b}`` for ``x-y-z``.
        """
        texts = path.split("/")
        if len(texts) != len(self._segments):
            return
        matchers: list[_Matcher] = []
        for segment, text in zip(self._segments, texts, strict=True):
            matcher = _segment_matcher(segment, text)
            if matcher is None:
                return
            matchers.append(matcher)
        yield from _match_all(matchers, {})

    def match(self, path: str) -> dict[str, str] | None:
        """
        The values ``path`` was formatted from, or ``None`` if it doesn't match.

        :raises ValueError: if ``path`` has more than one :meth:`parse`.
        """
        parses = list(islice(self.parse(path), 2))
        if len(parses) > 1:
            raise ValueError(f"{self!r} matches {path!r} in more than one way")
        return parses[0] if parses else None


def _parse_template(template: str) -> tuple[_Segment, ...]:
    segments: list[list[str | _Field]] = [[]]
    for literal, name, format_spec, conversion in string.Formatter().parse(template):
        head, *tail = literal.split("/")
        segments[-1].append(head)
        segments.extend([part] for part in tail)
        if name is None:
            continue
        if not name.isidentifier() or iskeyword(name):
            raise ValueError(f"Invalid parameter name {name!r} in path {template!r}")
        if conversion is not None and conversion not in _CONVERSIONS:
            raise ValueError(f"Invalid conversion '!{conversion}' in path {template!r}")
        if format_spec and "{" in format_spec:
            raise ValueError(f"Nested replacement field in path {template!r}")
        segments[-1].append(_Field(name, conversion, format_spec or ""))
    return tuple(tuple(part for part in segment if part) for segment in segments)


def _format_segment(segment: _Segment, values: Mapping[str, object]) -> str:
    formatted = "".join(
        part if isinstance(part, str) else part.render(values[part.name])
        for part in segment
    )
    if any(isinstance(part, _Field) for part in segment) and (
        unquote(formatted) in _DOT_SEGMENTS
    ):
        raise ValueError(f"Path segment {formatted!r} is empty or a dot-segment")
    return formatted


def _match_all(
    matchers: Sequence[_Matcher], values: dict[str, str]
) -> Iterator[dict[str, str]]:
    "Extend values with each matcher in turn."
    if not matchers:
        yield values
        return
    for found in matchers[0](values):
        yield from _match_all(matchers[1:], found)


def _segment_matcher(segment: _Segment, text: str) -> _Matcher | None:
    """
    Match text with segment: a function extending the values found so far in every
    way text can be formatted from segment, or None if it can't be.
    """
    if any(isinstance(part, _Field) for part in segment) and (
        unquote(text) in _DOT_SEGMENTS
    ):
        return None

    @cache
    def ends(i: int, start: int) -> tuple[int, ...]:
        "Where segment[i] can end if it starts at start, so the rest can match."
        part = segment[i]
        candidates: Iterable[int]
        if isinstance(part, str):
            candidates = [start + len(part)] if text.startswith(part, start) else []
        else:
            candidates = _value_ends(text, start)
        return tuple(end for end in candidates if matches(i + 1, end))

    def matches(i: int, start: int) -> bool:
        "Whether segment[i:] can match text[start:]."
        return start == len(text) if i == len(segment) else bool(ends(i, start))

    def extend(
        values: dict[str, str], i: int = 0, start: int = 0
    ) -> Iterator[dict[str, str]]:
        if i == len(segment):
            yield values
            return
        part = segment[i]
        for end in ends(i, start):
            if isinstance(part, str):
                yield from extend(values, i + 1, end)
                continue
            value = unquote(text[start:end])
            if values.get(part.name, value) == value:
                yield from extend({**values, part.name: value}, i + 1, end)

    return extend if matches(0, 0) else None


def _value_ends(text: str, start: int) -> Iterator[int]:
    "The ends of the values text can have from start: whole UTF-8 characters."
    decoder = getincrementaldecoder("utf-8")()
    end = start
    yield end
    while char := _SEGMENT_CHAR.match(text, end):
        end = char.end()
        try:
            decoder.decode(unquote_to_bytes(char.group()))
        except UnicodeDecodeError:
            return
        buffered, _ = decoder.getstate()
        if not buffered:  # not inside a multibyte character
            yield end


class endpoint:
    """
    Pass a url path, formatted from the arguments, as the first positional argument
    to the decorated function (after ``self`` for a method).

    .. code-block:: python

        @endpoint("foo/{foo_id}")
        def get_foo_by_id(url_path: str, foo_id: FooId):
            assert url_path == f"foo/{foo_id}"
            # but with foo_id properly escaped for path traversal injections.

        get_foo_by_id(foo_id)  # or get_foo_by_id(foo_id=foo_id)

    Every field in the path must name a parameter of the function, or the function
    must take ``**kwargs``. See :class:`PathTemplate` for how the path is formatted.
    """

    def __init__(self, path: str) -> None:
        self.template = PathTemplate(path)

    @overload
    def __call__(
        self, f: Callable[Concatenate[URLPath, _P], _T], /
    ) -> Callable[_P, _T]: ...
    @overload
    def __call__(
        self, f: Callable[Concatenate[_S, URLPath, _P], _T], /
    ) -> EndpointMethod[_S, _P, _T]: ...
    def __call__(self, f: Callable[..., object], /) -> object:
        return _Endpoint(self.template, f)


class _Endpoint:
    "A function decorated with :class:`endpoint`."

    def __init__(
        self, template: PathTemplate, f: Callable[..., object], *, method: bool = False
    ) -> None:
        sig = inspect.signature(f)
        params = list(sig.parameters.values())
        path_index = 1 if method else 0  # a method takes the url path after self
        self._template = template
        self._f = f
        self._sig = sig
        self._path_index = path_index
        self._var_keyword = _check_signature(template, f, params, path_index)
        update_wrapper(self, f)
        # the signature for callers, who don't pass the url path
        self.__signature__ = sig.replace(
            parameters=params[:path_index] + params[path_index + 1 :]
        )

    def __call__(self, *args: object, **kwargs: object) -> object:
        i = self._path_index
        if len(args) < i:
            raise TypeError(
                f"missing a required argument: {next(iter(self._sig.parameters))!r}"
            )
        before, after = args[:i], args[i:]
        bound = self._sig.bind(*before, None, *after, **kwargs)  # None for the path
        bound.apply_defaults()
        var_keyword: dict[str, object] = (
            bound.arguments[self._var_keyword] if self._var_keyword else {}
        )
        values: dict[str, object] = {**var_keyword, **bound.arguments}
        if missing := self._template.fields - values.keys():
            raise TypeError(
                f"missing a required path argument: {', '.join(sorted(missing))}"
            )
        url_path = self._template.format_map(values)
        return self._f(*before, url_path, *after, **kwargs)

    @cached_property
    def _method(self) -> _Endpoint:
        "This function as a method, which takes the url path after self."
        return _Endpoint(self._template, self._f, method=True)

    def __get__(
        self, instance: object, owner: type[object] | None = None
    ) -> _Endpoint | MethodType:
        method = self if self._path_index else self._method
        return method if instance is None else MethodType(method, instance)


def _check_signature(
    template: PathTemplate,
    f: Callable[..., object],
    params: list[inspect.Parameter],
    path_index: int,
) -> str | None:
    """
    Check the decorated function takes the url path and the template's fields.

    Return the name of its ``**kwargs`` parameter, if it has one.
    """
    positional = (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    )
    if len(params) <= path_index or params[path_index].kind not in positional:
        raise TypeError(f"{f!r} takes no positional url path argument")
    named = {
        p.name
        for p in params[path_index + 1 :]
        if p.kind in (*positional, inspect.Parameter.KEYWORD_ONLY)
    }
    if reserved := template.fields & ({p.name for p in params} - named):
        raise TypeError(f"Path fields {sorted(reserved)} can't be filled by {f!r}")
    var_keyword = next(
        (p.name for p in params if p.kind is inspect.Parameter.VAR_KEYWORD), None
    )
    if var_keyword is None and (unknown := template.fields - named):
        raise TypeError(f"Path fields {sorted(unknown)} are not parameters of {f!r}")
    return var_keyword
