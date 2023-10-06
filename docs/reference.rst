=============
API reference
=============

``APIClient`` class
===================

The ``APIClient`` class extends requests' :class:`requests.Session`, requiring you
to provide a ``base_url``.

.. autoclass:: ape_pie.APIClient
    :members:

.. _config_adapter:

Configuration adapters
======================

Configuration adapters need to be implemented by your project, so that a client instance
can be configured from your configuration source. It essentially acts as a translation
from your domain-specific configuration to :class:`ape_pie.APIClient` arguments.

Configuration adapters must implement our protocol:

.. autoclass:: ape_pie.ConfigAdapter
    :members:
