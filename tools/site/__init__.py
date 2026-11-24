"""Static site generator for pentool.pro.

Layout of the package:

* ``config.py`` — the only place with URLs, contacts, prices and the language list;
* ``render.py`` — one page shell plus a small set of content blocks;
* ``content/<lang>.py`` — page texts, one module per language, identical structure;
* ``build.py`` — writes ``docs/`` and refuses to build when translations diverge.

Usage::

    python tools/site/build.py           # regenerate docs/
    python tools/site/build.py --check   # only verify language parity
"""
