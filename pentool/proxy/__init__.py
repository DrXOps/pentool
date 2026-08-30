"""Proxy isolation layer (П.3): a daemon process + a TUI facade.

The proxy lives in its OWN process, not inside the TUI. The TUI talks to it
only over a local unix socket (commands in, events out). This is what removes
the whole class of 'proxy-on-a-daemon-thread shares memory/EventBus with the
TUI' failures (mouse-race, run() returned while proxy alive, shields the app
from proxy-side state).
"""

from __future__ import annotations
