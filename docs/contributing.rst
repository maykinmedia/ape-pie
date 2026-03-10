============
Contributing
============

Release flow
============

Bump the version number using bump-my-version:

.. code-block:: bash

    bump-my-version bump major|minor|patch

Update ``CHANGELOG.rst`` with the new version, release date and included changes.

Then, to actually release to PyPI, tag the release commit and push it:

.. code-block:: bash

    git tag <new-version>
    git push origin <new-version>

The CI pipeline will publish it if all checks pass.
