.. _contribute:

Contribute to EOM
=================

`Kurt Griffiths <http://kgriffs.com>`_ is the creator of EOM which is now maintained by
`Benjamen R. Meyer <http://github.com/BenjamenMeyer>`_ and
`Sriram Madapusi Vasudevan <https://github.com/TheSriram/>`_.
Everyone, like yourself, is welcome to contribute too by reviewing patches, implementing
features, fixing bugs, and writing documentation for the project.

Ideas and patches are always welcome.

Bugs, Feature, Requests, etc
----------------------------

We use the features of GitHub as a project management tool. If you have a bug
or feature request, please file in our `GitHub Issues <https://github.com/racker/eom/issues>`_.

Pull Requests
-------------

Before submitting a pull request, please update any existing tests and add any
new tests as appropriate. We are working towards 100% test coverage. Also please
ensure your coding style is PEP 8 compliant.

Please also reference any `GitHub Issues <https://github.com/racker/eom/issues>`_
your pull request fixes or contributes towards by using the
`GitHub Markdown <https://guides.github.com/features/mastering-markdown/#GitHub-flavored-markdown>`_
information for Issues.

* Note: Presently the EOM uWSGI Logger's unit test is not reliable. Please run the tests several times to verify they pass if this is the test that is failing.

**Additional Style Rules**

* When in doubt, optimize for readability.
* Don't try to be clever; but if you must, document it extensively.
* Do not use single letter variables except for the well-known trivial values when looping (e.g i, k, v)
