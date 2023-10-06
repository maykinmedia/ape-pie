==========
Quickstart
==========

Installation
============

Install from PyPI with pip:

.. code-block:: bash

    pip install ape-pie


Usage
=====

The recommended usage is to instantiate a client (a :class:`requests.Session`, we'll
call them clients from here on) from a configuration adapter in your domain:

.. code-block:: python

    from ape_pie import APIClient

    from .adapters import my_adapter


    client = APIClient.configure_from(my_adapter)

    with client:
        # ⚡️ context manager -> uses connection pooling and is recommended!
        response1 = client.get("some-relative-path", params={"foo": ["bar"]})
        response2 = client.post("other-path", json={...})


The ``my_adapter`` object is a "special" :ref:`configuration source <config_adapter>`,
which feeds the relevant initialization parameters to the :class:`ape_pie.client.APIClient`
instance.

.. note:: You can (and should) use the client/session in a context manager to benefit
   from connection pooling and thus better performance when multiple requests are made.

You can also instantiate clients directly:

.. code-block::

    from ape_pie import APIClient
    from requests.auth import HTTPBasicAuth

    # You can pass most attributes available on requests.Session, like auth/verify/cert...
    client = APIClient(
        "https://example.com/api/v1/",
        auth=HTTPBasicAuth("superuser", "letmein"),
        verify="/path/to/custom/ca-bundle.pem",
    )

    with client:
        # ⚡️ context manager -> uses connection pooling and is recommended!
        response1 = client.get("some-relative-path", params={"foo": ["bar"]})
        response2 = client.post("other-path", json={...})

    ...

Configuration adapter example
-----------------------------

Suppose you are keeping your client parameters in a TOML file:

.. code-block:: toml

    api-root = "https://example.com"

    [auth]
    type = "basic"
    username = "admin"
    password = "letmein"

    [headers]
    Accept = "application/json"


You could then implement a configuration adapter grabbing the root, auth and headers
configuration:

.. code-block:: python

    import tomllib
    from typing import Any

    from requests.auth import HTTPBasicAuth


    class TOMLConfigAdapter:

        def __init__(self, config_file: str):
            with open(config_file, "rb") as f:
                self.config = tomllib.load(f)

        def get_client_base_url(self) -> str:
            return self.config["api-root"]

        def get_client_session_kwargs(self) -> dict[str, Any]:
            auth = None
            if (auth := self.config["auth"])["type"] == "basic":
                auth = HTTPBasicAuth(auth["username"], auth["password"])
            return {
                "auth": auth,
                "headers": self.config["headers"],
            }

and use it as:

.. code-block:: python

    toml_adapter = TOMLConfigAdapter("/tmp/config.toml")
    client = APIClient.configure_from(toml_adapter)

    with client:
        r = client.get("foo")
        ...
