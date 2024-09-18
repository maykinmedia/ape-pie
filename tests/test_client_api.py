import pytest
from requests import Session
from requests.auth import HTTPBasicAuth

from ape_pie import APIClient
from ape_pie.typing import RequestKwargs


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

    client = APIClient("https://example.com", {attr: value})  # type: ignore[assignment]

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
