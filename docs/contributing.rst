============
Contributing
============

Release flow
============

Bump the version number using tbump:

.. code-block:: bash

    tbumb --only-patch <new-version>

Update ``CHANGELOG.rst`` with the new version, release date and included changes.

Then, to actually release to PyPI, tag the release commit and push it:

.. code-block:: bash

    git tag <new-version>
    git push origin <new-version>

The CI pipeline will publish it if all checks pass.
