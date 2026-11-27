from collections import OrderedDict
from urllib.parse import unquote
from uuid import UUID

import pytest
from hypothesis import example, given, reject, strategies as st
from requests import Session
from requests.auth import HTTPBasicAuth
from requests.cookies import RequestsCookieJar
from requests.structures import CaseInsensitiveDict

from ape_pie import APIClient, InvalidURLError
from ape_pie.decorators import PathTemplate, path_escape
from ape_pie.typing import RequestKwargs

BASE_URLS = [
    "https://example.com",
    "https://example.com/",
    "https://example.com/api/v1",
    "https://example.com/api/v1/",
]


@pytest.mark.parametrize("attr", Session.__attrs__)
def test_defaults_from_requests_session(attr):
    vanilla_session = Session()
    client = APIClient("https://example.com")

    if attr == "adapters":
        return

    vanilla_value = getattr(vanilla_session, attr)
    client_value = getattr(client, attr)

    assert client_value == vanilla_value


@pytest.mark.parametrize(
    "attr,value",
    [
        ("auth", HTTPBasicAuth("superuser", "letmein")),
        ("verify", False),
        ("cert", ("/tmp/cert.pem", "/tmp/key.pem")),
    ],
)
def test_can_override_defaults(attr, value):
    # sanity check for test itself
    assert attr in Session.__attrs__
    vanilla_session = Session()

    client = APIClient("https://example.com", {attr: value})  # type: ignore[arg-type, misc]

    vanilla_value = getattr(vanilla_session, attr)
    client_value = getattr(client, attr)
    assert client_value != vanilla_value
    assert client_value == value


def test_config_does_not_mutate():
    imported_settings: RequestKwargs = {
        "auth": ("djkhaled", "youplayedyourself"),
    }

    class MyConfig:
        @staticmethod
        def get_client_base_url():
            return "https://example.com"

        @staticmethod
        def get_client_session_kwargs():
            return imported_settings

    one = APIClient.configure_from(MyConfig)
    another_one = APIClient.configure_from(MyConfig)

    assert one.auth == ("djkhaled", "youplayedyourself")
    assert another_one.auth == ("djkhaled", "youplayedyourself")


@pytest.mark.parametrize(
    "attr,value,expected_type",
    [
        ("headers", {"Foo": "Bar"}, CaseInsensitiveDict),
        ("cookies", {"SessionID": "totallyunguessable"}, RequestsCookieJar),
        ("auth", None, None),
        ("auth", HTTPBasicAuth("superuser", "letmein"), HTTPBasicAuth),
        ("proxies", {"http": "localhost:8888"}, dict),
        # unsure if this should overwrite or (deep) merge by default
        ("hooks", {"response": []}, dict),
        ("params", {"foo": "bar"}, dict),
        ("verify", True, bool),
        ("verify", "/tmp/ca.pem", str),
        ("cert", ("/tmp/cert.pem", "/tmp/key.pem"), tuple),
        ("cert", "/tmp/cert.pem", str),
        ("adapters", {}, OrderedDict),
        ("stream", False, bool),
        ("trust_env", True, bool),
        ("max_redirects", 3, int),
    ],
)
def test_client_request_kwargs_dont_mess_up_requests_types(
    attr: str, value: object, expected_type: type[object] | None
):
    # take just the single attribute and verify it
    kwargs: RequestKwargs = {}
    kwargs[attr] = value
    client = APIClient("https://example.com", kwargs)

    result = getattr(client, attr)

    if expected_type is None:
        assert result is None
    else:
        assert isinstance(result, expected_type)


def test_headers_extend_or_overwrite_default_headers():
    client = APIClient(
        "https://example.com",
        request_kwargs={"headers": {"user-agent": "test/client"}},
    )

    # from requests' default_headers
    assert "accept" in client.headers
    # overwrite requests' default_headers
    assert client.headers["User-Agent"] == "test/client"


# relative paths as PathTemplate formats them, from one that doesn't start with "/"
relative_paths = st.builds(
    lambda first, rest: "/".join(map(path_escape, [first, *rest])),
    st.text(min_size=1),
    st.lists(st.text()),
)


@pytest.mark.parametrize("base_url", BASE_URLS)
@given(path=relative_paths)
@example(path="")
def test_to_relative_url_inverts_to_absolute_url(base_url: str, path: str):
    client = APIClient(base_url)

    relative_url = client.to_relative_url(client.to_absolute_url(path))

    # path_escape gives "foo%3Abar", which furl normalises to "foo:bar"
    assert decoded(relative_url) == decoded(path)


def decoded(path: str) -> list[str]:
    return [unquote(segment) for segment in path.split("/")]


@pytest.mark.parametrize(
    "base_url,url",
    [
        ("https://example.com/api/v1", "https://example.com/api/v10/zaken/1"),
        ("https://example.com/api/v1/", "https://example.com/api/zaken/1"),
        ("https://example.com/api/v1/", "http://example.com/api/v1/zaken/1"),
        ("https://example.com/api/v1/", "https://other.example.com/api/v1/zaken/1"),
        ("https://example.com", "https://example.com.evil.net/zaken/1"),
    ],
)
def test_to_relative_url_rejects_urls_outside_the_base_url(base_url: str, url: str):
    with pytest.raises(InvalidURLError):
        APIClient(base_url).to_relative_url(url)


ZAAKEIGENSCHAP = PathTemplate("zaken/{zaak_uuid}/zaakeigenschappen/{uuid}")


@pytest.mark.parametrize("base_url", BASE_URLS)
@given(zaak_uuid=st.text(), uuid=st.text())
@example(zaak_uuid=str(UUID(int=1)), uuid=str(UUID(int=2)))
@example(zaak_uuid="a,b", uuid="c")
def test_matches_the_values_of_a_resource_url(base_url: str, zaak_uuid: str, uuid: str):
    client = APIClient(base_url)
    try:
        path = ZAAKEIGENSCHAP.format(zaak_uuid=zaak_uuid, uuid=uuid)
    except ValueError:
        # zaak_uuid or uuid is "", "." or "..": a server would read
        # "zaken/../zaakeigenschappen/1" as "zaakeigenschappen/1"
        reject()
    # as an API returns it: furl normalises "zaken/a%2Cb/…" to "zaken/a,b/…"
    url = client.to_absolute_url(path)

    assert ZAAKEIGENSCHAP.match(client.to_relative_url(url)) == {
        "zaak_uuid": zaak_uuid,
        "uuid": uuid,
    }
