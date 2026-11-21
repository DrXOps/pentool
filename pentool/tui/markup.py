"""Escaping text that lands in Rich markup.

``RichLog(markup=True)`` and ``Static`` (which has ``markup=True`` by default)
parse their text as Rich markup. Text that came from outside — an HTTP
response body, a URL from traffic, a path from the sitemap snapshot, the stderr
of an external tool, a licensing server reply — must not get into markup:

* ``[/]`` with no opening tag — ``MarkupError`` right inside the message
  handler: the log line is lost and the exception goes to the Textual
  dispatcher;
* ``[link=javascript:…]`` builds a clickable link with a dangerous target.
  The TUI itself has no browser, but the same body is reused in the HTML
  reports (``export/``), where the link does work.

Rule: our own markup goes in literally, a foreign value goes through :func:`esc`::

    log.write(f"[bold]{esc(host)}[/bold] — {count} requests")

Only the value is escaped, not the whole line: ``escape()`` over a string that
already carries our tags would show those tags to the user literally.
"""

from __future__ import annotations

from rich.markup import escape


def esc(value: object) -> str:
    """Return ``value`` as text: ``[`` and ``]`` in it will not become markup."""
    return escape(str(value))
