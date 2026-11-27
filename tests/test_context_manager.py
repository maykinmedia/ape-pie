from collections.abc import Iterator
from unittest import mock

import pytest
import requests_mock as rm
from requests.adapters import HTTPAdapter

from ape_pie import APIClient


@pytest.fixture
def client() -> APIClient:
    return APIClient("https://example.com/api/")


@pytest.fixture
def close_spy(client: APIClient) -> Iterator[mock.MagicMock]:
    with mock.patch.object(client, "close", wraps=client.close) as spy:
        yield spy


def test_enter_returns_client(client: APIClient) -> None:
    with client as outer, client as inner:
        assert outer is client
        assert inner is client


def test_nested_context_managers_only_close_on_outer_exit(
    client: APIClient, close_spy: mock.MagicMock
) -> None:
    with client:
        with client:
            with client:
                pass
            close_spy.assert_not_called()

        close_spy.assert_not_called()

    close_spy.assert_called_once_with()


def test_requests_in_nested_blocks_do_not_close_session(
    client: APIClient, close_spy: mock.MagicMock, requests_mock: rm.Mocker
) -> None:
    requests_mock.get("https://example.com/api/foo", json={"ok": True})

    with client:
        with client:
            client.get("foo")

        close_spy.assert_not_called()
        client.get("foo")
        close_spy.assert_not_called()

    close_spy.assert_called_once_with()


def test_connection_pools_survive_inner_exit(client: APIClient) -> None:
    adapter = client.get_adapter("https://example.com/api/")
    assert isinstance(adapter, HTTPAdapter)

    with client:
        # simulate a pooled connection having been established
        adapter.poolmanager.connection_from_url("https://example.com/api/")
        assert len(adapter.poolmanager.pools) == 1

        with client:
            pass

        assert len(adapter.poolmanager.pools) == 1

    assert len(adapter.poolmanager.pools) == 0


def test_exception_in_inner_block_does_not_close_session(
    client: APIClient, close_spy: mock.MagicMock
) -> None:
    with client:
        with pytest.raises(ValueError), client:
            raise ValueError("boom")

        close_spy.assert_not_called()

    close_spy.assert_called_once_with()


def test_exception_propagates_through_outer_block(
    client: APIClient, close_spy: mock.MagicMock
) -> None:
    with pytest.raises(ValueError), client, client:
        raise ValueError("boom")

    close_spy.assert_called_once_with()


def test_client_can_be_reused_after_exiting(
    client: APIClient, close_spy: mock.MagicMock, requests_mock: rm.Mocker
) -> None:
    requests_mock.get("https://example.com/api/foo", json={"ok": True})

    with client, client:
        client.get("foo")
    assert close_spy.call_count == 1

    with client:
        with client:
            client.get("foo")
        assert close_spy.call_count == 1
    assert close_spy.call_count == 2


def test_request_outside_context_manager_closes_session(
    client: APIClient, close_spy: mock.MagicMock, requests_mock: rm.Mocker
) -> None:
    requests_mock.get("https://example.com/api/foo", json={"ok": True})

    client.get("foo")

    close_spy.assert_called_once_with()
